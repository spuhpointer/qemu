# Address-dependent diagnostic for the tested AIX media; verify symbols for other builds.
# gdb script: log IEEE 1275 client-interface calls of the AIX CHRP boot
# program (32-bit cells) to run/ci-trace.log.
# Usage: gdb -x aix.gdb -x ci-trace.py   (VM started with GDB_WAIT=1)
import gdb, os
from pathlib import Path

ENTRY = 0x6134                  # bootfile.exe ELF e_entry
LOG = os.path.join(os.environ.get("RUN_DIR", str(Path(__file__).resolve().parents[2] / "run-aix73")), "ci-trace.log")
Path(LOG).parent.mkdir(parents=True, exist_ok=True)
out = open(LOG, "w", buffering=1)
inf = gdb.selected_inferior()


def u32(a):
    return int.from_bytes(bytes(inf.read_memory(a, 4)), "big")


def cstr(a, n=256):
    if a == 0:
        return ""
    b = bytes(inf.read_memory(a, n))
    return b.split(b"\0")[0].decode("latin-1")


def reg(r):
    return int(gdb.parse_and_eval("$" + r)) & 0xffffffff


class CiBreak(gdb.Breakpoint):
    def stop(self):
        a = reg("r3")
        svc = cstr(u32(a), 64)
        nargs, nret = u32(a + 4), u32(a + 8)
        args = [u32(a + 12 + 4 * i) for i in range(nargs)]
        txt = ""
        if svc in ("getprop", "getproplen", "nextprop") and nargs >= 2:
            txt = " name=%r" % cstr(args[1], 64)
        elif svc in ("finddevice", "open"):
            txt = " %r" % cstr(args[0], 128)
        elif svc == "write" and nargs >= 3:
            txt = " %r" % cstr(args[1], min(args[2], 200))
        elif svc in ("call-method", "interpret"):
            txt = " %r" % cstr(args[0], 128)
        out.write("lr=%08x %s%s args=%s\n" % (reg("lr"), svc, txt,
                                              [hex(x) for x in args]))
        if svc == "write" and "unsupported" in txt:
            out.write("=== unsupported message, backtrace by LR chain:\n")
            sp = reg("r1")
            for _ in range(12):
                if sp == 0:
                    break
                out.write("  sp=%08x saved_lr=%08x\n" % (sp, u32(sp + 8)))
                sp = u32(sp)
        return False


eb = gdb.Breakpoint("*0x%x" % ENTRY, internal=True)
gdb.execute("continue")
ci = reg("r5")
out.write("entry: r3=%08x r4=%08x r5(ci)=%08x\n" % (reg("r3"), reg("r4"), ci))
eb.delete()
CiBreak("*0x%x" % ci, internal=True)
gdb.execute("continue")
