# Address-dependent diagnostic for the tested AIX media; verify symbols for other builds.
# gdb script: log entries to interrupt vectors 0x200 (machine check), 0x300,
# 0x400, 0x700 after the AIX kernel starts. Output: run/vec-trace.log
import gdb, os
from pathlib import Path
LOG = os.path.join(os.environ.get("RUN_DIR", str(Path(__file__).resolve().parents[2] / "run-aix73")), "vec-trace.log")
Path(LOG).parent.mkdir(parents=True, exist_ok=True)
out = open(LOG, "w", buffering=1)
def reg(r):
    return int(gdb.parse_and_eval("$" + r)) & 0xffffffffffffffff
class Vec(gdb.Breakpoint):
    def stop(self):
        out.write("vector %s: srr0=%016x srr1=%016x lr=%016x dar=%016x dsisr=%08x\n"
                  % (self.location, reg("srr0"), reg("srr1"), reg("lr"),
                     reg("dar"), reg("dsisr")))
        return self.location == "*0x700"
kstart = gdb.Breakpoint("*0x101c98", internal=True)   # AIX kernel entry_point
gdb.execute("continue")
kstart.delete()
out.write("kernel entry reached\n")
for v in ("*0x200", "*0x300", "*0x400", "*0x700"):
    Vec(v, internal=True)
gdb.execute("continue")
gdb.execute("detach")
