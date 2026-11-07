#!/usr/bin/env python3
"""Operate this workspace's QEMU console and QMP monitor."""
import argparse
import json
import pathlib
import re
import select
import socket
import os
import sys
import termios
import time
import tty

RUN = pathlib.Path(os.environ.get("RUN_DIR", pathlib.Path(__file__).resolve().parents[2] / "run-aix73"))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("interface", choices=("console", "relay", "qmp", "hmp"))
parser.add_argument("command", nargs="?", default="")
parser.add_argument("--wait", type=float, default=3)
parser.add_argument("--run", default=str(RUN))
args = parser.parse_args()
RUN = pathlib.Path(args.run).resolve()
sock = socket.socket(socket.AF_UNIX)
sock.settimeout(args.wait)
sock.connect(str(RUN / ("console.sock" if args.interface in ("console", "relay") else "qmp.sock")))
if args.interface == "relay":
    # QEMU already logs received output. Drain it without filling a PTY buffer.
    previous = termios.tcgetattr(0)
    tty.setraw(0)
    sock.settimeout(None)
    try:
        while True:
            ready, _, _ = select.select([sock, 0], [], [])
            if sock in ready and not sock.recv(65536):
                break
            if 0 in ready:
                chunk = os.read(0, 65536)
                if not chunk or chunk == b"\x1d":
                    break
                sock.sendall(chunk)
    finally:
        termios.tcsetattr(0, termios.TCSADRAIN, previous)
elif args.interface == "console":
    sock.sendall(args.command.encode() + b"\r")
    end = time.monotonic() + args.wait
    data = bytearray()
    while time.monotonic() < end:
        sock.settimeout(max(0.01, end - time.monotonic()))
        try:
            part = sock.recv(65536)
        except socket.timeout:
            break
        if not part:
            break
        data.extend(part)
    print(re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", data.decode(errors="replace")))
else:
    stream = sock.makefile("rwb", buffering=0)
    json.loads(stream.readline())
    def request(command, arguments=None):
        msg = {"execute": command}
        if arguments is not None:
            msg["arguments"] = arguments
        stream.write(json.dumps(msg).encode() + b"\n")
        while True:
            reply = json.loads(stream.readline())
            if "return" in reply or "error" in reply:
                return reply
    request("qmp_capabilities")
    if args.interface == "hmp":
        result = request("human-monitor-command", {"command-line": args.command})
    else:
        result = request(args.command)
    if "error" in result:
        print(json.dumps(result["error"]), file=sys.stderr)
        sys.exit(1)
    print(result["return"] if args.interface == "hmp" else json.dumps(result["return"], indent=2))
sock.close()
