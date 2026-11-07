#!/usr/bin/env bash
# Build this checkout; all outputs remain local and must not be committed.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
case "${1:-release}" in
    release) BUILD="${BUILD_DIR:-$ROOT/build}"; DIST="${DIST_DIR:-$ROOT/dist}"; EXTRA=() ;;
    debug) BUILD="${BUILD_DIR:-$ROOT/build-debug}"; DIST="${DIST_DIR:-$ROOT/dist-debug}"; EXTRA=(--enable-debug) ;;
    *) echo "usage: $0 [release|debug]" >&2; exit 2 ;;
esac
mkdir -p "$BUILD" "$DIST"
BUILD="$(cd "$BUILD" && pwd)"
DIST="$(cd "$DIST" && pwd)"
HOST=()
case "$(uname -s)" in
    Darwin) HOST=(--enable-vmnet --enable-cocoa) ;;
    Linux) ;;
    *) echo 'This helper documents macOS and Linux hosts only.' >&2; exit 1 ;;
esac
AIX_PYTHON="${PYTHON:-}"
if [ -z "$AIX_PYTHON" ]; then
    for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            AIX_PYTHON="$(command -v "$candidate")"
            break
        fi
    done
fi
[ -n "$AIX_PYTHON" ] || { echo 'Install Python 3.9+ first (3.11+ recommended).' >&2; exit 1; }
cd "$BUILD"
"$ROOT/configure" --python="$AIX_PYTHON" --prefix="$DIST" --target-list=ppc64-softmmu \
    --enable-slirp --enable-gnutls --enable-zstd --enable-tools --disable-docs \
    "${HOST[@]}" "${EXTRA[@]}"
make -j "${JOBS:-4}" install
"$AIX_PYTHON" "$HERE/make-slof-aix.py"
echo "Built $DIST/bin/qemu-system-ppc64"
