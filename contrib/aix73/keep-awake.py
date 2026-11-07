#!/usr/bin/env python3
"""Keep this Mac and its disks awake only while the launched QEMU exists."""
from pathlib import Path
import shutil
import subprocess
import sys

run = Path(sys.argv[1]).resolve()
pid = int((run / "qemu.pid").read_text().strip())
binary = shutil.which("caffeinate")
if binary:
    with (run / "caffeinate.log").open("ab") as log:
        child = subprocess.Popen(
            [binary, "-im", "-w", str(pid)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            close_fds=True, start_new_session=True,
        )
    (run / "caffeinate.pid").write_text(f"{child.pid}\n")
