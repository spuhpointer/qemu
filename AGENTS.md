# AGENTS.md — AIX 7.3 compatibility work

## Scope and baseline

This branch contains source changes for running a user's independently
licensed AIX 7.3 TL3 SP1 (`7300-03-01-2520`) on QEMU pseries. Its upstream
baseline is tag `v11.1.3`, commit
`005c61c0ef6f6ae615283440b4bb7be51b2c6ddd`.

Never push. Commit only when explicitly requested. Preserve unrelated user
changes. Keep fixes in QEMU or its open-source firmware; do not patch AIX
kernel/application binaries or copy proprietary IBM firmware.

The reference configuration is POWER9, TCG, XICS, four vCPUs, 4 GiB RAM,
two NUMA nodes, one vSCSI disk and a reserved CD-ROM drive. Apple Silicon
cannot hardware-accelerate a POWER guest. The Linux x86 build also uses TCG.
Other AIX releases, CPU models and topologies are not covered by the same
end-to-end validation.

## Source-only and privacy requirements

- Stage explicit source/documentation paths; never use an indiscriminate
  repository-wide add after running a VM.
- Do not stage generated executables, firmware images, disk images, ISOs,
  logs, sockets, PID files, credentials, SSH keys/known hosts, guest dumps,
  extracted AIX files, installer payloads or machine-specific configuration.
- Keep VM disks/media outside this checkout. Runtime state defaults to
  ignored `run-aix73/`; isolated tests can use `run-aix73-*/`.
- Examples must use placeholders or caller-selected paths. Do not include
  personal filesystem paths, volume names, host identities, passwords,
  public/private user keys, UUIDs, PVIDs or unrelated project information.
- `aix73-qemu.patch` and `slof-prep-limit.patch` are text source patches.
  The patched SLOF output must be generated locally and remain ignored.
- Review `git diff --cached --numstat` for binary entries and inspect the
  complete staged path list before reporting readiness for publication.

## Layout and builds

QEMU source is at the repository root, not in a nested `src/` directory.
Portable helpers are in `contrib/aix73/`. The main `README.rst` is the
operating/build guide; `wordpress.txt` is a publication draft.

```
JOBS=8 ./contrib/aix73/build-qemu.sh
JOBS=8 ./contrib/aix73/build-qemu.sh debug
```

The release build installs to `dist/`, debug to `dist-debug/`, and SLOF is
generated in `build-aix-firmware/`. `BUILD_DIR` and `DIST_DIR` can relocate
build outputs. The Linux recipe omits macOS Cocoa/vmnet options.

Changes to the 13 QEMU files in the original patch should remain synchronized
with `contrib/aix73/aix73-qemu.patch`. Export only those source paths against
the baseline tag; do not accidentally include private files or the patch
inside itself. The source files already include the patch: do not apply it
again to this branch.

## Operation

Set an absolute `DISK` path explicitly. Use only the owner's licensed media.
Read the README before running installation, which can overwrite a selected
guest disk. The launcher refuses to start over a live PID in its state
directory. Prefer a guest `shutdown -Fh` before replacing a QEMU process.

```
export DISK=/absolute/path/to/aix.qcow2
export RUN_DIR="$PWD/run-aix73"
DAEMONIZE=1 CONSOLE=sock ./contrib/aix73/run-aix.sh
./contrib/aix73/ssh-aix.sh
```

The default final profile enables both `aix-compat` and `aix-papr`, two NUMA
nodes, and XICS. The bootstrap/diagnostic QEMU-mode profile is
`AIX_PAPR=off NUMA_SPLIT=0 SMP=4`; ASO intentionally rejects that mode.

`CDROM` selects read-only media. Unset uses the private `RUN_DIR/cdrom.path`;
an explicitly empty value leaves the drive empty. The CD drive is always
reserved because this vSCSI bus cannot hot-add a drive. Unmount media inside
AIX before using HMP `change cd0 ... raw` to change it.

Localhost SSH forwarding defaults to 2222 and optional telnet to 2323.
GDB binds localhost:1234. Use separate state directories, disk overlays and
ports for experiments. Do not run two writers against one qcow2 image.
`keep-awake.py` binds a macOS sleep inhibitor to the VM's PID.

## Diagnostics

- `RUN_DIR/console.log`: guest serial output. A serial reader must drain
  output during verbose boots. `vmctl.py relay` accepts raw input and drains
  output to the existing log; Ctrl-] disconnects the helper.
- `RUN_DIR/qemu.log`: emulation warnings and selected trace events.
  `DLOG=unimp,guest_errors` and `TRACE=/absolute/path/to/events` are configurable.
- `python3 contrib/aix73/vmctl.py hmp 'info registers'`
- `python3 contrib/aix73/vmctl.py qmp query-status`
- `GDB_WAIT=1` starts stopped. Use `gdb -x contrib/aix73/aix.gdb` with big-endian
  `powerpc:common64`. A batch GDB detach resumes the VM.
- `numa-vec-trace.py`, `vec-trace.py`, `msr-trace.py`, `slb-trace.py` and
  `ci-trace.py` contain addresses specific to the examined AIX build. Verify
  them before use with another kernel. The CI helper is historical and did
  not reliably fire in the original investigation.
- Do not create GDB breakpoints inside a Breakpoint.stop callback.
- Guest KDB supports stack (`f`), registers (`dr`), disassembly (`dc`) and
  memory (`dd`) inspection. Short `dc ADDRESS 18` requests avoid its pager.
- HMP `dumpdtb` needs an absolute output path because daemonized QEMU changes
  its working directory. Use `dtc` to inspect the result; keep it private.

## Compatibility findings to preserve

1. The media's boot loader rejects stock `qemu,pseries`; its built-in QEMU
   mode recognizes `qemu,pseriesNOPE`. Native PAPR uses `IBM,pSeries`.
2. AIX real-mode accesses require the 1 TiB VRMA segment wrap. The opt-in
   CPU flag masks real-mode addresses to 40 bits.
3. XIVE was not usable in this setup. XICS works; native AIX also requires a
   16-byte zero `reg` property on the XICS device-tree node.
4. Existing vSCSI paths require stable disk identification. The
   `x-aix-vscsi-id` property supplies standard-INQUIRY vendor bytes and a T10
   VPD 0x83 identifier. Native discovery needs an encoded LUN-zero address.
5. The generic vSCSI DMA cursor was only 16 bits. A 256 KiB direct request
   crossed 128 KiB SCSI callbacks, wrapped the cursor to zero, and overwrote
   or repeated data. Keep `cur_desc_offset` at 32 bits. This fixed LED 0552
   and the volume-group metadata failure.
6. Native ASO needs discoverable DSCR controls (`ibm,pa-optimizations`),
   processor-capacity reporting (`H_GET_PPP`) and enhanced affinity.
7. AIX validates the CPU leaf level in `ibm,max-associativity-domains`.
   Native multi-node mode advertises five levels and includes the complete
   interrupt-server-number range, including sparse IDs.
8. The bundled SLOF PREP loader limit is too small for the tested boot image.
   The local generation recipe and source patch raise it to 256 MiB.

ASO running does not provide POWER hardware acceleration or model real POWER
cache timing. Large-page promotion can legitimately hibernate with 4 GiB RAM.
Some optional hypercalls and hardware-diagnostics services remain unsupported.

## Validation

Run the AIX-independent tests without licensed media:

```
python3 contrib/aix73/test-vscsi-large-io.py
python3 contrib/aix73/test-vscsi-large-io.py --aix-papr
python3 contrib/aix73/test-vscsi-large-io.py --numa
python3 contrib/aix73/test-vscsi-large-io.py --aix-papr --numa
```

They exercise actual POWER hypercalls, CRQs and SCSI DMA, including distinct
data across 128 KiB boundaries, direct/indirect reads and writes, REPORT LUNS,
processor capacity and NUMA-domain metadata. The QEMU virtio-scsi qtests also
cover opt-in inquiry identification and unchanged default behavior.

The reference AIX VM passed clean restart, SSH/network/DNS checks, distinct
chunk disk-integrity tests and multi-hour operation with ASO active. It used
the original AIX kernel, application binaries, boot script and fsck tools.
Do not ship its runtime evidence: reproduce checks and retain logs privately.

One earlier runtime had transient backend I/O failures after a long idle
interval. Reopening the image restored access; a leaked unused qcow2 cluster
was reclaimed offline, with no structural corruption reported. Its exact
cause was not proven. Keep sleep inhibition and I/O error tracing, and do
not claim exhaustive reliability or support for every AIX feature.
