"""GDB guest script: capture the first early NUMA-boot storage exception."""
import gdb
import os
from pathlib import Path

run = Path(os.environ.get("RUN_DIR", Path(__file__).resolve().parents[2] / "run-aix73"))
run.mkdir(parents=True, exist_ok=True)
out = (run / "numa-vec.log").open("w", buffering=1)

def reg(name):
    return int(gdb.parse_and_eval("$" + name)) & 0xffffffffffffffff

entry = gdb.Breakpoint("*0x101c98", internal=True)
gdb.execute("continue")
entry.delete()
out.write("kernel entry reached\n")

class Vector(gdb.Breakpoint):
    def stop(self):
        pc = reg("srr0")
        out.write(f"{self.location} srr0={pc:016x} srr1={reg('srr1'):016x} "
                  f"lr={reg('lr'):016x} dar={reg('dar'):016x} "
                  f"dsisr={reg('dsisr'):08x} r1={reg('r1'):016x}\n")
        if self.location == "*0x700" and 0x90bee0 <= pc <= 0x90bf10:
            return False
        out.write(gdb.execute("info registers", to_string=True))
        try:
            out.write(gdb.execute(f"x/12i 0x{pc - 16:x}", to_string=True))
        except gdb.error as exc:
            out.write(str(exc) + "\n")
        return True

for address in (0x200, 0x300, 0x400, 0x700):
    Vector(f"*0x{address:x}", internal=True)
gdb.execute("continue")
gdb.execute("detach")
