#!/bin/ksh
# Run INSIDE AIX as root. Packages and keys come from your mounted IBM media.
set -e
[ "$(uname -s)" = AIX ] || { echo 'Run this helper inside AIX, not on the host.' >&2; exit 1; }
[ "$(id -u)" = 0 ] || { echo 'Run as root inside AIX.' >&2; exit 1; }
MEDIA=${1:-/mnt/toolbox}
case "$MEDIA" in /*) ;; *) echo 'The media mount path must be absolute.' >&2; exit 1 ;; esac
INSTALLER="$MEDIA/ezinstall/ppc/dnf_aixtoolbox_local.sh"
[ -x "$INSTALLER" ] || { echo "Mount the Toolbox binary ISO at $MEDIA first." >&2; exit 1; }

grow_if_smaller()
{
    current=$(df -m "$1" | awk 'NR == 2 { print int($2) }')
    [ -n "$current" ] || { echo "Cannot determine size of $1" >&2; exit 1; }
    if [ "$current" -lt "$2" ]; then
        chfs -a "size=${2}M" "$1"
    fi
}

rpm -qa > "/var/tmp/aix73-rpm-before-toolbox-$(date +%Y%m%d%H%M%S).txt"
if [ "${RESIZE_FILESYSTEMS:-1}" = 1 ]; then
    # Only grow; never shrink a filesystem that is already larger.
    grow_if_smaller /opt 4096
    grow_if_smaller /tmp 1024
    grow_if_smaller /var 1024
fi
if [ ! -x /opt/freeware/bin/dnf ]; then
    "$INSTALLER" "$MEDIA"
else
    echo 'DNF already exists; leaving its existing repository configuration intact.'
fi
rpm --import /opt/freeware/etc/dnf/RPM-GPG-KEY-IBM-AIX-Toolbox
if [ ! -f /.profile ] || ! grep -q 'AIX Toolbox command path' /.profile; then
    if [ -f /.profile ]; then
        cp -p /.profile "/.profile.before-toolbox-$(date +%Y%m%d%H%M%S)"
    fi
    cat >> /.profile <<'PROFILE'

# AIX Toolbox command path (keep native AIX utilities first).
case ":$PATH:" in
    *:/opt/freeware/bin:*) ;;
    *) PATH="$PATH:/opt/freeware/bin"; export PATH ;;
esac
PROFILE
fi
/opt/freeware/bin/yum --version
/opt/freeware/bin/dnf repolist
/opt/freeware/bin/yum check
echo 'Toolbox package management is ready; reconnect to use yum from PATH.'
