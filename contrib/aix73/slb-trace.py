# Address-dependent diagnostic for the tested AIX media; verify symbols for other builds.
# gdb script: log slbmte operands in AIX slb_nmi_check (0x53EB10: slbmte r0,r5)
# and the first program interrupt (vector 0x700). Output: run/slb-trace.log
import gdb, os
from pathlib import Path
LOG = os.path.join(os.environ.get("RUN_DIR", str(Path(__file__).resolve().parents[2] / "run-aix73")), "slb-trace.log")
Path(LOG).parent.mkdir(parents=True, exist_ok=True)
out = open(LOG, "w", buffering=1)
def reg(r):
    return int(gdb.parse_and_eval("$" + r)) & 0xffffffffffffffff
class Slb(gdb.Breakpoint):
    def stop(self):
        out.write("slbmte rs(r0)=%016x rb(r5)=%016x msr=%016x lr=%016x\n"
                  % (reg("r0"), reg("r5"), reg("msr"), reg("lr")))
        return False
class Prog(gdb.Breakpoint):
    def stop(self):
        out.write("program interrupt: srr0=%016x srr1=%016x\n"
                  % (reg("srr0"), reg("srr1")))
        return True
Slb("*0x53eb10", internal=True)
Prog("*0x700", internal=True)
gdb.execute("continue")
gdb.execute("detach")
