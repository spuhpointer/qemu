#!/usr/bin/env python3
"""Exercise real pseries vSCSI DMA using a tiny, kernel-free POWER guest.

No AIX media or disk is used. Each 256 KiB request crosses QEMU's 128 KiB
SCSI DMA chunk boundary. Distinct page patterns catch descriptor-offset
wraparound on both reads and writes, with direct and indirect descriptors.
"""
import argparse
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time


class Remote:
    def __init__(self, sock):
        self.sock = sock
        self.command("qSupported:xmlRegisters=powerpc")
        self.command("qXfer:features:read:target.xml:0,1000")
        self.command("?")

    def command(self, text):
        data = text.encode()
        self.sock.sendall(b"$" + data + b"#" + f"{sum(data) & 255:02x}".encode())
        while True:
            byte = self.sock.recv(1)
            if not byte:
                raise RuntimeError("GDB connection closed")
            if byte == b"$":
                break
        result = bytearray()
        while True:
            byte = self.sock.recv(1)
            if byte == b"#":
                break
            if not byte:
                raise RuntimeError("GDB connection closed")
            result.extend(byte)
        checksum = bytearray()
        while len(checksum) < 2:
            byte = self.sock.recv(2 - len(checksum))
            if not byte:
                raise RuntimeError("GDB connection closed during checksum")
            checksum.extend(byte)
        assert int(checksum, 16) == sum(result) & 255
        self.sock.sendall(b"+")
        reply = result.decode()
        if reply.startswith("E"):
            raise RuntimeError(f"GDB {text[:80]}: {reply}")
        return reply

    def reg(self, number, value=None):
        if value is None:
            return int(self.command(f"p{number:x}"), 16)
        assert self.command(f"P{number:x}={value:016x}") == "OK"

    def write(self, addr, data):
        for off in range(0, len(data), 1024):
            chunk = data[off:off + 1024]
            assert self.command(f"M{addr + off:x},{len(chunk):x}:{chunk.hex()}") == "OK"

    def read(self, addr, size):
        result = bytearray()
        for off in range(0, size, 1024):
            length = min(1024, size - off)
            result.extend(bytes.fromhex(self.command(f"m{addr + off:x},{length:x}")))
        return bytes(result)

    def hcall(self, opcode, *args, expected=0):
        self.reg(3, opcode)
        for i, arg in enumerate(args, 4):
            self.reg(i, arg)
        self.reg(64, 0x10000)
        assert self.command("s").startswith(("T05", "S05"))
        result = self.reg(3)
        assert result == expected, f"hcall {opcode:#x} returned {result:#x}, expected {expected:#x}"


def pattern(seed):
    return b"".join(bytes([(i + seed) % 251]) * 4096 for i in range(64))


def test(remote, disk, aix_papr, cores):
    bus, queue, iu, table, data_addr = 0x71000002, 0x20000, 0x30000, 0x31000, 0x100000
    size = 256 * 1024
    remote.reg(65, 0x8000000000001000)  # 64-bit supervisor, translation off
    remote.write(0x10000, bytes.fromhex("44000022"))  # sc 1
    if aix_papr:
        remote.hcall(0xec)  # H_GET_PPP, emulated processor pool
        capacity = cores * 100
        assert remote.reg(4) == capacity
        assert remote.reg(5) == 0
        assert remote.reg(6) == cores << 32
        assert remote.reg(7) == (1 << 48) | (128 << 40) | (cores << 16) | cores
        assert remote.reg(8) == (cores << 48) | (capacity << 24) | capacity
        print("PASS native PAPR processor capacity", flush=True)
    else:
        remote.hcall(0xec, expected=(1 << 64) - 2)  # Default stays H_FUNCTION.
    remote.write(queue, bytes(4096))
    for addr in [queue, iu, table] + list(range(data_addr, data_addr + size, 4096)):
        remote.hcall(0x20, bus, addr, addr | 3)  # H_PUT_TCE
    remote.hcall(0xfc, bus, queue, 4096)  # H_REG_CRQ
    queue_index = 0

    def send(crq):
        nonlocal queue_index
        remote.hcall(0x108, bus, *struct.unpack(">QQ", crq))
        slot = queue + queue_index * 16
        deadline = time.monotonic() + 10
        while not remote.read(slot, 1)[0]:
            if time.monotonic() > deadline:
                raise RuntimeError("vSCSI response timeout")
            time.sleep(0.001)
        response = remote.read(slot, 16)
        remote.write(slot, bytes(16))
        queue_index += 1
        return response

    def request(payload):
        remote.write(iu, payload + bytes(256 - len(payload)))
        send(struct.pack(">BBBBHHQ", 0x80, 1, 0, 0, 0, len(payload), iu))
        return remote.read(iu, 64)

    send(bytes.fromhex("c0010000000000000000000000000000"))
    login = bytearray(64)
    struct.pack_into(">Q", login, 8, 1)
    struct.pack_into(">I", login, 16, 256)
    struct.pack_into(">H", login, 24, 6)
    assert request(login)[0] == 0xc0

    def scsi(opcode, writing=False, indirect=False, length=size):
        cmd = bytearray(48)
        cmd[0] = 2
        struct.pack_into(">Q", cmd, 8, queue_index + 1)
        struct.pack_into(">Q", cmd, 20, 0 if opcode == 0xa0 else 0x8000000000000000)
        cmd[32] = opcode
        if length:
            cmd[5] = (2 if indirect else 1) << (4 if writing else 0)
            cmd[6 if writing else 7] = 1
            if opcode == 0xa0:
                struct.pack_into(">I", cmd, 38, length)
            else:
                struct.pack_into(">H", cmd, 39, length // 512)
            descriptor = struct.pack(">QII", data_addr, 0, length)
            if indirect:
                remote.write(table, descriptor)
                cmd.extend(struct.pack(">QIII", table, 0, 16, length))
            cmd.extend(descriptor)
        response = request(cmd)
        assert response[0] == 0xc1
        return response[19]

    assert scsi(0, length=0) == 2  # Consume power-on unit attention.
    assert scsi(0, length=0) == 0
    assert scsi(0xa0, length=32) == 0
    luns = remote.read(data_addr, 16)
    assert struct.unpack_from(">I", luns)[0] == 8
    assert struct.unpack_from(">Q", luns, 8)[0] == (0x8000000000000000 if aix_papr else 0)
    print("PASS REPORT LUNS addressing", flush=True)
    expected = pattern(0)
    for indirect in (False, True):
        kind = "indirect" if indirect else "direct"
        remote.write(data_addr, bytes([0xee]) * size)
        assert scsi(0x28, indirect=indirect) == 0
        actual = remote.read(data_addr, size)
        assert actual == expected, f"{kind} READ_10 data mismatch across 128 KiB boundary"
        print(f"PASS {kind} 256 KiB READ_10", flush=True)
        expected = pattern(71 if indirect else 37)
        remote.write(data_addr, expected)
        assert scsi(0x2a, writing=True, indirect=indirect) == 0
        assert scsi(0x35, length=0) == 0  # SYNCHRONIZE CACHE
        assert disk.read_bytes()[:size] == expected, f"{kind} WRITE_10 data mismatch"
        print(f"PASS {kind} 256 KiB WRITE_10", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", default=str(Path(__file__).resolve().parents[2] / "dist/bin/qemu-system-ppc64"))
    parser.add_argument("--aix-papr", action="store_true")
    parser.add_argument("--numa", action="store_true")
    args = parser.parse_args()
    qemu = str(Path(args.qemu).resolve())
    with tempfile.TemporaryDirectory(prefix="aix-vscsi-test-") as tmp:
        root = Path(tmp)
        disk = root / "test.raw"
        disk.write_bytes(pattern(0) + bytes(768 * 1024))
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.close()
        with (root / "qemu.log").open("w+") as log:
            numa_args = [
                "-object", "memory-backend-ram,id=m0,size=256M",
                "-object", "memory-backend-ram,id=m1,size=256M",
                "-numa", "node,nodeid=0,cpus=0,memdev=m0",
                "-numa", "node,nodeid=1,cpus=1,memdev=m1",
            ] if args.numa else []
            monitor = root / "monitor.sock"
            proc = subprocess.Popen([
                qemu, "-M", "pseries,ic-mode=xics" +
                (",aix-compat=on,aix-papr=on" if args.aix_papr else "") +
                (",vsmt=8" if args.numa else ""),
                "-cpu", "POWER9",
                "-m", "512" if args.numa else "256",
                "-smp", "2,sockets=2,cores=1,threads=1" if args.numa else "1",
                "-S", "-nodefaults", "-display", "none",
                "-monitor", f"unix:{monitor},server=on,wait=off", "-serial", "none",
                "-gdb", f"tcp:127.0.0.1:{port}",
                "-device", "spapr-vscsi,id=scsi0,reg=0x71000002",
                "-drive", f"file={disk},format=raw,if=none,id=disk",
                "-device", "scsi-hd,drive=disk,bus=scsi0.0,scsi-id=0,lun=0",
            ] + numa_args, stdout=subprocess.DEVNULL, stderr=log)
            try:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        sock = socket.create_connection(("127.0.0.1", port), 1)
                        break
                    except ConnectionRefusedError:
                        if proc.poll() is not None or time.monotonic() > deadline:
                            log.seek(0)
                            raise RuntimeError(log.read())
                        time.sleep(0.05)
                with sock:
                    sock.settimeout(10)
                    if args.numa:
                        tree = root / "tree.dtb"
                        with socket.socket(socket.AF_UNIX) as mon:
                            mon.connect(str(monitor))
                            mon.sendall(f"dumpdtb {tree}\n".encode())
                            deadline = time.monotonic() + 5
                            while not tree.exists():
                                if time.monotonic() > deadline:
                                    raise RuntimeError("Device tree dump timed out")
                                time.sleep(0.01)
                        blob = tree.read_bytes()
                        struct_start, strings_start = struct.unpack_from(">II", blob, 8)
                        name = blob.index(b"ibm,max-associativity-domains\0", strings_start)
                        levels = 5 if args.aix_papr else 4
                        marker = struct.pack(">III", 3, (levels + 1) * 4, name - strings_start)
                        prop = blob.index(marker, struct_start) + 12
                        domains = struct.unpack_from(">" + "I" * (levels + 1), blob, prop)
                        assert domains[:5] == (levels, 2, 2, 2, 2)
                        if args.aix_papr:
                            assert domains[5] == 16  # Two cores, VSMT eight.
                        print("PASS NUMA maximum associativity domains", flush=True)
                    test(Remote(sock), disk, args.aix_papr, 2 if args.numa else 1)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


if __name__ == "__main__":
    main()
