#!/bin/bash
# Run AIX on emulated POWER (pseries, TCG), with debug interfaces.
#
# First install: DISK=/absolute/path/to/aix.qcow2 ./run-aix.sh install /path/to/aix.iso
# Normal boot:   DISK=/absolute/path/to/aix.qcow2 ./run-aix.sh
#
# NET=user    (default) slirp NAT, no root; host port 2222 -> guest ssh 22,
#             2323 -> telnet 23. Guest: 10.0.2.15/24 gw 10.0.2.2, DNS 10.0.2.3.
# NET=shared  macOS vmnet NAT, guest gets a reachable 192.168.x address (sudo).
# NET=bridged macOS vmnet bridged onto BRIDGE_IF (default en0) (sudo).
#
# QEMU_BUILD=debug  use the -O0 --enable-debug build (dist-debug), slower.
# GDB_WAIT=1        freeze CPUs at start until gdb attaches and continues.
# TRACE=file        trace event patterns (default run/trace.events).
# IC_MODE=mode      interrupt controller xics (default), xive or dual.
# BOOT_ARGS=args    AIX boot arguments for disk boots, e.g. "-s verbose".
# DLOG=flags        QEMU -d log flags (default unimp,guest_errors; e.g. +int).
# DISK_ID=id        stable AIX virtual SCSI identity; keep it with this disk.
# DAEMONIZE=1       detach QEMU itself (requires CONSOLE=sock).
# AIX_PAPR=off      use legacy AIX QEMU mode (native PAPR is the default).
# NUMA_SPLIT=0      disable the two-node topology used for enhanced affinity.
# CDROM=path        read-only ISO for disk boots; unset uses RUN_DIR/cdrom.path.
#                   Set CDROM='' for an empty drive. A CD drive is always present.
# CONSOLE=sock      serial console on $RUN_DIR/console.sock instead of this terminal
#                   (attach: socat -,raw,echo=0,escape=0x1d unix-connect:$RUN_DIR/console.sock;
#                   Ctrl-] detaches). The VM then runs detached from the terminal.
#
# Debug interfaces, all under RUN_DIR (default REPO/run-aix73):
#   console.log  serial console copy (console stays on this terminal;
#                Ctrl-A x quits, Ctrl-A c toggles the HMP monitor)
#   qemu.log     -d unimp,guest_errors output and trace events
#   qmp.sock     QMP:  socat - unix-connect:$RUN_DIR/qmp.sock
#   hmp.sock     HMP:  socat - unix-connect:$RUN_DIR/hmp.sock
#   qemu.pid     host QEMU pid, for lldb -p
#   tcp :1234    guest gdbstub: gdb -x aix.gdb  (big-endian ppc64)
set -e
umask 077
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
if [ "$QEMU_BUILD" = "debug" ]; then
    DIST="${DIST_DIR:-$ROOT/dist-debug}"
else
    DIST="${DIST_DIR:-$ROOT/dist}"
fi
QEMU="${QEMU_BIN:-$DIST/bin/qemu-system-ppc64}"
FIRMWARE="${FIRMWARE:-$ROOT/build-aix-firmware/slof-aix.bin}"
RUN="${RUN_DIR:-$ROOT/run-aix73}"
case "$RUN" in /*) ;; *) RUN="$PWD/$RUN" ;; esac
: "${DISK:?Set DISK to your own absolute VM disk path, preferably outside this checkout}"
case "$DISK" in /*) ;; *) echo "DISK must be an absolute path" >&2; exit 1 ;; esac
DISK_SIZE="${DISK_SIZE:-40G}"
MEM="${MEM:-4096}"
SMP="${SMP:-4,sockets=2,cores=2,threads=1}"
CPU="${CPU:-POWER9}"
NET="${NET:-user}"
AIX_PAPR="${AIX_PAPR:-on}"
NUMA_SPLIT="${NUMA_SPLIT:-1}"
GDB_PORT="${GDB_PORT:-1234}"
TRACE="${TRACE:-$RUN/trace.events}"
if [ -z "${CDROM+x}" ] && [ -r "$RUN/cdrom.path" ]; then
    CDROM="$(cat "$RUN/cdrom.path")"
fi

[ -x "$QEMU" ] || { echo "Build QEMU first: contrib/aix73/build-qemu.sh" >&2; exit 1; }
[ -f "$FIRMWARE" ] || { echo "Generate SLOF first: python3 contrib/aix73/make-slof-aix.py" >&2; exit 1; }
INSTALL_MEDIA="${2:-}"
case "$INSTALL_MEDIA" in ""|/*) ;; *) INSTALL_MEDIA="$PWD/$INSTALL_MEDIA" ;; esac
case "$CDROM" in ""|/*) ;; *) CDROM="$PWD/$CDROM" ;; esac
case "${1:-boot}" in
    boot) [ -f "$DISK" ] || { echo "Disk missing; run install mode first" >&2; exit 1; } ;;
    install) [ -f "${2:-}" ] || { echo "usage: $0 install /absolute/path/to/aix.iso" >&2; exit 1; } ;;
    *) echo "usage: $0 [boot | install /absolute/path/to/aix.iso]" >&2; exit 1 ;;
esac
if [ -r "$RUN/qemu.pid" ]; then
    OLD_PID="$(cat "$RUN/qemu.pid")"
    if [[ "$OLD_PID" =~ ^[0-9]+$ ]] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "VM already running (PID $OLD_PID); shut it down before starting another" >&2
        exit 1
    fi
fi
case "$TRACE" in /*) ;; *) TRACE="$PWD/$TRACE" ;; esac
mkdir -p "$RUN"
if [ ! -f "$RUN/trace.events" ]; then
    cat > "$RUN/trace.events" <<'EOF'
spapr_rtas_*
spapr_cas_*
spapr_ovec_*
spapr_h_*
spapr_drc_*
spapr_pci_*
spapr_vio_*
spapr_update_*
spapr_vlan_h_*
spapr_vscsi_process_login
spapr_vscsi_command_complete_status
scsi_disk_rw_error
scsi_disk_emulate_command_UNKNOWN
scsi_req_parse_bad
EOF
fi

if [ ! -f "$DISK" ]; then
    mkdir -p "$(dirname "$DISK")"
    "$DIST/bin/qemu-img" create -f qcow2 "$DISK" "$DISK_SIZE"
fi

SUDO=
case "$NET" in
    user)    NETDEV="user,id=net0,hostfwd=tcp:127.0.0.1:${SSH_PORT:-2222}-:22,hostfwd=tcp:127.0.0.1:${TELNET_PORT:-2323}-:23" ;;
    shared)  NETDEV="vmnet-shared,id=net0"; SUDO=sudo ;;
    bridged) NETDEV="vmnet-bridged,id=net0,ifname=${BRIDGE_IF:-en0}"; SUDO=sudo ;;
    *) echo "unknown NET=$NET" >&2; exit 1 ;;
esac

ARGS=(
    -name aix
    -accel tcg
    -bios "$FIRMWARE"
    -machine pseries,aix-compat=on,aix-papr=$AIX_PAPR,ic-mode=${IC_MODE:-xics},cap-cfpc=broken,cap-sbbc=broken,cap-ibs=broken,cap-ccf-assist=off
    -cpu "$CPU" -smp "$SMP" -m "$MEM"
    -nographic
    -qmp "unix:$RUN/qmp.sock,server=on,wait=off"
    -monitor "unix:$RUN/hmp.sock,server=on,wait=off"
    -gdb "tcp:127.0.0.1:$GDB_PORT"
    -pidfile "$RUN/qemu.pid"
    -d "${DLOG:-unimp,guest_errors}" -D "$RUN/qemu.log"
    -trace "events=$TRACE"
    -msg timestamp=on
    -device spapr-vscsi,id=scsi0
    -drive "file=${DISK//,/,,},if=none,id=hd0,format=qcow2,cache=writeback"
    -device "scsi-hd,drive=hd0,bus=scsi0.0,x-aix-vscsi-id=${DISK_ID:-qemu-aix73-rootvg}"
    -netdev "$NETDEV"
    -device spapr-vlan,netdev=net0
)

if [ "$NUMA_SPLIT" = "1" ]; then
    VCPU_COUNT="${SMP%%,*}"
    case "$MEM:$VCPU_COUNT" in
        *[!0-9:]*) echo 'NUMA_SPLIT requires numeric MEM in MiB and SMP count' >&2; exit 1 ;;
    esac
    [ "$VCPU_COUNT" -ge 2 ] && [ "$((VCPU_COUNT % 2))" -eq 0 ] &&
        [ "$((MEM % 512))" -eq 0 ] || {
        echo 'NUMA_SPLIT requires an even vCPU count and MEM divisible by 512' >&2
        exit 1
    }
    ARGS+=(
        -object "memory-backend-ram,id=ram0,size=$((MEM / 2))M"
        -object "memory-backend-ram,id=ram1,size=$((MEM / 2))M"
        -numa "node,nodeid=0,cpus=0-$((VCPU_COUNT / 2 - 1)),memdev=ram0"
        -numa "node,nodeid=1,cpus=$((VCPU_COUNT / 2))-$((VCPU_COUNT - 1)),memdev=ram1"
    )
fi

if [ "$CONSOLE" = "sock" ]; then
    ARGS+=(
        -chardev "socket,id=con0,path=$RUN/console.sock,server=on,wait=off,logfile=$RUN/console.log,logappend=on"
        -serial chardev:con0
    )
else
    ARGS+=(
        -chardev "stdio,id=con0,mux=on,signal=off,logfile=$RUN/console.log,logappend=on"
        -serial chardev:con0
        -mon chardev=con0,mode=readline
    )
fi

if [ "$GDB_WAIT" = "1" ]; then
    ARGS+=(-S)
fi

if [ "$DAEMONIZE" = "1" ]; then
    [ "$CONSOLE" = "sock" ] || { echo 'DAEMONIZE=1 requires CONSOLE=sock' >&2; exit 1; }
    ARGS+=(-daemonize -parallel none)
fi

if [ "$1" = "install" ]; then
    [ -f "$2" ] || { echo "usage: $0 install <aix.iso>" >&2; exit 1; }
    ARGS+=(
        -drive "file=${INSTALL_MEDIA//,/,,},if=none,id=cd0,format=raw,media=cdrom,readonly=on"
        -device scsi-cd,id=cdrom0,drive=cd0,bus=scsi0.0,scsi-id=1,lun=0
        -prom-env "boot-command=boot cdrom: -s verbose"
    )
else
    if [ -n "$CDROM" ]; then
        [ -f "$CDROM" ] || { echo "CDROM does not exist: $CDROM" >&2; exit 1; }
        ARGS+=(-drive "file=${CDROM//,/,,},if=none,id=cd0,format=raw,media=cdrom,readonly=on")
    else
        ARGS+=(-drive if=none,id=cd0,media=cdrom,readonly=on)
    fi
    ARGS+=(-device scsi-cd,id=cdrom0,drive=cd0,bus=scsi0.0,scsi-id=1,lun=0)
    ARGS+=(-prom-env "boot-command=boot disk: ${BOOT_ARGS}")
fi

echo "logs/sockets in $RUN (qemu: $QEMU)" >&2
if [ "$DAEMONIZE" = "1" ]; then
    $SUDO "$QEMU" "${ARGS[@]}"
    if command -v caffeinate >/dev/null 2>&1; then
        python3 "$HERE/keep-awake.py" "$RUN"
    fi
    exit 0
fi
exec $SUDO "$QEMU" "${ARGS[@]}"
