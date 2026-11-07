#!/bin/sh
# Use only a key generated and installed by this VM's owner.
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/../.." && pwd)
RUN=${RUN_DIR:-$ROOT/run-aix73}
KEY=${SSH_KEY:-$RUN/aix_ed25519}
[ -r "$KEY" ] || { echo "Create your own SSH key and install its public key in AIX; see README.rst." >&2; exit 1; }
exec ssh -i "$KEY" \
    -o IdentitiesOnly=yes \
    -o ConnectTimeout=15 \
    -o UserKnownHostsFile="$RUN/ssh_known_hosts" \
    -p "${SSH_PORT:-2222}" "${SSH_USER:-root}@127.0.0.1" "$@"
