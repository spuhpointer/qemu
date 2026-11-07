#!/usr/bin/env python3
"""Generate local AIX-compatible SLOF from QEMU's bundled open-source image.

The embedded Forth change is fixed length, preserving the image layout.
For a full firmware source rebuild, see slof-prep-limit.patch and README.rst.
No generated firmware belongs in the staged contribution.
"""
import argparse
from pathlib import Path

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, default=root / "pc-bios/slof.bin")
parser.add_argument("--output", type=Path,
                    default=root / "build-aix-firmware/slof-aix.bin")
args = parser.parse_args()
old = b"d# 65536 value max-prep-partition-blocks"
new = b"h# 80000 value max-prep-partition-blocks"
data = args.source.read_bytes()
if len(old) != len(new) or data.count(old) != 1:
    raise SystemExit("Unexpected SLOF image; inspect its PREP limit before changing it")
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_bytes(data.replace(old, new))
print(f"Generated {args.output}: PREP limit 32 MiB -> 256 MiB")
