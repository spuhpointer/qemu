# Address-dependent diagnostic for the tested AIX media; verify symbols for other builds.
# gdb script: log MSR/SLB-relevant state at AIX kernel milestones.
# Output: run/msr-trace.log
import gdb, os
from pathlib import Path
LOG = os.path.join(os.environ.get("RUN_DIR", str(Path(__file__).resolve().parents[2] / "run-aix73")), "msr-trace.log")
Path(LOG).parent.mkdir(parents=True, exist_ok=True)
out = open(LOG, "w", buffering=1)
def reg(r):
    return int(gdb.parse_and_eval("$" + r)) & 0xffffffffffffffff
POINTS = {0x101c98: "kernel entry", 0x11f4880: "main", 0x11feb40: "vmsi",
          0x1200620: "init_early_pgspace", 0x9a9360: "is_a_vios"}
class P(gdb.Breakpoint):
    def stop(self):
        a = reg("pc")
        out.write("%-20s pc=%016x msr=%016x lr=%016x r1=%016x\n"
                  % (POINTS.get(a, "?"), a, reg("msr"), reg("lr"), reg("r1")))
        return a == 0x9a9360
for a in POINTS:
    P("*0x%x" % a, internal=True)
gdb.execute("continue")
gdb.execute("detach")
