Running AIX 7.3 on patched QEMU
===============================

This branch makes an independently licensed AIX 7.3 installation usable on
QEMU's emulated POWER platform. The reference system ran AIX 7.3 TL3 SP1
(``7300-03-01-2520``) on an Apple M2 Pro using TCG, with four POWER9 vCPUs,
4 GiB RAM, XICS interrupts, two virtual NUMA nodes, and a 40 GiB qcow2 disk.
It booted from disk, accepted console and SSH logins, passed disk-integrity
and network tests, and ran Active System Optimizer (ASO).

This is a source contribution: QEMU fixes, source patches, helpers and build
instructions. No compiled QEMU executable, generated firmware, AIX media,
installed disk, credentials or guest dump is distributed by this contribution.
Obtain and use your own appropriately licensed AIX and Toolbox media.
The firmware involved here is open-source SLOF, not proprietary IBM firmware.

The profile is experimental and tested in the configuration above. It is not
a complete PowerVM implementation or a claim of IBM support. POWER on Apple
Silicon or an x86 Linux host uses software emulation; HVF and x86 KVM cannot
hardware-accelerate this cross-architecture guest. ASO can monitor and manage
guest workloads, but it cannot turn TCG into real POWER hardware.

1. Get the correct source branch
--------------------------------

The baseline is QEMU ``v11.1.3`` at commit
``005c61c0ef6f6ae615283440b4bb7be51b2c6ddd``. The example URL assumes these
changes have been published as branch ``aix73-papr``; substitute the owner or
branch if publishing elsewhere. Check out the branch containing the fixes,
not an older unrelated branch in the fork.

.. code-block:: sh

   git clone --branch aix73-papr https://github.com/spuhpointer/qemu.git qemu-aix73
   cd qemu-aix73
   cat VERSION
   git status --short

The QEMU source files in this branch already contain the fixes.
``contrib/aix73/aix73-qemu.patch`` is a text export for a clean upstream
v11.1.3 checkout; do not apply it again to this branch. Helpers live in
``contrib/aix73/``. ``AGENTS.md`` records maintenance and privacy rules.

2. Build on macOS
-----------------

Install Apple's command-line developer tools and the Homebrew dependencies.
The debugger tools are optional for ordinary use.

.. code-block:: sh

   xcode-select --install
   brew install glib pixman libslirp ninja gnutls zstd pkgconf python
   brew install socat gdb dtc radare2
   JOBS=10 ./contrib/aix73/build-qemu.sh

The helper prefers an installed modern Python interpreter; ``PYTHON`` can
select one explicitly. This avoids accidentally using an incomplete system
Python environment. It configures only ``ppc64-softmmu``, installs the
optimized build into ``dist/``, and generates local SLOF firmware under
``build-aix-firmware/``. The generated directories are ignored by Git.

The equivalent manual configure/build sequence is:

.. code-block:: sh

   mkdir -p build
   cd build
   ../configure --prefix="$PWD/../dist" --target-list=ppc64-softmmu \
     --enable-slirp --enable-vmnet --enable-cocoa --enable-gnutls \
     --enable-zstd --enable-tools --disable-docs
   make -j10 install
   cd ..
   python3 contrib/aix73/make-slof-aix.py
   ls -l build/qemu-system-ppc64 dist/bin/qemu-system-ppc64

If configure selects an unsuitable Python, pass ``--python=/path/to/python3``.
The launcher uses the installed ``dist/`` executable, so rebuilding without
installing does not update the VM executable.

3. Build on Linux
-----------------

For Debian/Ubuntu hosts, install the development dependencies and use the
same helper. On another distribution, use its equivalent package names.
This recipe is provided for rebuilding the source on Linux; the AIX
end-to-end reference validation was performed on the macOS host.

.. code-block:: sh

   sudo apt-get update
   sudo apt-get install build-essential git python3 python3-venv python3-pip \
     python3-tomli pkg-config ninja-build libglib2.0-dev libpixman-1-dev \
     libslirp-dev libgnutls28-dev libzstd-dev socat device-tree-compiler
   JOBS=8 ./contrib/aix73/build-qemu.sh

The helper omits ``--enable-vmnet`` and ``--enable-cocoa`` on Linux.
User-mode NAT remains the simplest network setup. An x86 Linux server still
uses TCG for the POWER guest; tap/bridge integration is a separate host setup.

For a debug build, use the following. Debug TCG is much slower; use the
optimized build for installation and ordinary operation.

.. code-block:: sh

   JOBS=8 ./contrib/aix73/build-qemu.sh debug
   # Select it when launching a VM:
   QEMU_BUILD=debug CONSOLE=sock DAEMONIZE=1 ./contrib/aix73/run-aix.sh

``BUILD_DIR`` and ``DIST_DIR`` relocate build outputs. The launcher accepts
``DIST_DIR`` or ``QEMU_BIN`` when using a non-default installation prefix.
Set ``DISK`` as described below before launching either build.

4. Generate or rebuild SLOF locally
-----------------------------------

The bundled SLOF PREP boot loader limits reads to 32 MiB, while the tested
AIX bosboot image is larger. The build helper runs ``make-slof-aix.py`` to
raise this limit to 256 MiB in a locally generated image. It changes one
fixed-length embedded Forth expression and refuses an unexpected input.
It uses QEMU's existing public SLOF asset; no modified binary is added to Git.

.. code-block:: sh

   python3 contrib/aix73/make-slof-aix.py
   # The launcher defaults to:
   # build-aix-firmware/slof-aix.bin

A source-build alternative is also supplied. On a Linux host with a
big-endian PowerPC64 cross compiler, build the pinned open-source SLOF
submodule after applying the text patch:

.. code-block:: sh

   sudo apt-get install gcc-powerpc64-linux-gnu binutils-powerpc64-linux-gnu
   git submodule update --init roms/SLOF
   git -C roms/SLOF apply ../../contrib/aix73/slof-prep-limit.patch
   make -C roms/SLOF CROSS=powerpc64-linux-gnu- -j4 qemu
   mkdir -p build-aix-firmware
   cp roms/SLOF/boot_rom.bin build-aix-firmware/slof-aix.bin

Apply the SLOF source patch once to its clean pinned checkout. The
reproducible bundled-image transformation was used in the reference setup;
the cross-build commands follow SLOF's own build procedure. ``FIRMWARE`` can
select another locally built image. Do not stage any generated firmware.

5. Choose private storage and licensed media
--------------------------------------------

Keep disks and media outside the source checkout. Choose a volume with
enough space for the 40 GiB virtual disk to grow, plus any local snapshots
and backups. A small system volume is a poor place for VM storage.
Edit the media path below to point to your own AIX installation image.

.. code-block:: sh

   export VM_DIR="$HOME/VirtualMachines/aix73"
   # An external disk or another filesystem can be used instead.
   mkdir -p "$VM_DIR"
   export DISK="$VM_DIR/aix.qcow2"
   export RUN_DIR="$PWD/run-aix73"
   mkdir -p "$RUN_DIR"
   chmod 700 "$RUN_DIR"
   export INSTALL_ISO="/absolute/path/to/your/AIX_7.3_install.iso"

The launcher requires an absolute ``DISK`` path and never embeds a
workstation-specific default. Install mode creates a missing qcow2 image;
boot mode refuses a missing disk. It also refuses to start over a live PID
in the selected state directory. Do not have the ISO mounted by the host
while QEMU opens it: host mounting can conflict with QEMU's read lock.

6. Install AIX through the serial console
-----------------------------------------

To reproduce the validated sequence, bootstrap the installation in AIX's
built-in QEMU mode, then switch to native PAPR after the first login. The
final default profile is native PAPR; the explicit options below select
the bootstrap mode. Only attach the new VM disk you intend to install onto.

.. code-block:: sh

   AIX_PAPR=off NUMA_SPLIT=0 SMP=4 DAEMONIZE=1 CONSOLE=sock \
     ./contrib/aix73/run-aix.sh install "$INSTALL_ISO"
   socat -,raw,echo=0,escape=0x1d "unix-connect:$RUN_DIR/console.sock"

* At 'Please define the System Console', enter the selection shown on that console.
* Choose the installation language and review the installation settings. Menu numbers can differ between media levels.
* For a new blank VM, choose the intended installation method, confirm the virtual disk and size, and complete BOS installation. An overwrite installation destroys the contents of the selected guest disk.
* Allow kernel loading, device configuration and package installation to finish. TCG installation and first-boot file checks can take considerable time.
* Ctrl-] disconnects socat without shutting down the VM. The serial socket accepts one client at a time.
* Once installation has completed, launch from the installed disk. Install mode deliberately boots CD media, so an automatic reboot of that same QEMU process can return to the installer.

If the installer has finished and returned to firmware or the installer,
stop that completed install session with the monitor, then start disk mode.
Do not use monitor quit during installation or normal writable guest work.

.. code-block:: sh

   python3 contrib/aix73/vmctl.py qmp quit
   AIX_PAPR=off NUMA_SPLIT=0 SMP=4 DAEMONIZE=1 CONSOLE=sock \
     ./contrib/aix73/run-aix.sh
   socat -,raw,echo=0,escape=0x1d "unix-connect:$RUN_DIR/console.sock"

Finish AIX's first-boot assistant. ``vt100`` is a useful terminal choice.
Review and accept the applicable terms, complete the assistant, and log in
as root. Set your own root password; do not copy someone else's credentials
or save them in the public checkout. Leave the original AIX kernel,
application binaries, boot scripts and fsck tools in place.

The bootstrap mode can report that ASO is unsupported on KVM. That is why
the final native-PAPR profile is provided. No AIX binary patch or forced
boot-device edit is needed with the QEMU fixes in this branch.

7. Configure the guest network
------------------------------

The default user-mode network requires no host root privileges. It provides
NAT and forwards localhost port 2222 to guest SSH port 22. Inside AIX, as
root, configure the virtual Ethernet interface and DNS:

.. code-block:: sh

   mktcpip -h aix73 -a 10.0.2.15 -m 255.255.255.0 -i en0 -g 10.0.2.2
   namerslv -a -i 10.0.2.3
   ifconfig en0
   ping -c 3 10.0.2.2
   host www.ibm.com

The DNS step is separate because ``mktcpip -n`` requires a domain argument.
These addresses are QEMU's private NAT defaults, not a physical LAN setup.
You can set your own hostname and timezone; for example, ``chtz UTC0`` sets
UTC for new sessions.

``NET=shared`` and ``NET=bridged`` use macOS vmnet and require elevated
host privileges; their sockets can become root-owned. ``BRIDGE_IF`` selects
the bridge interface. The simple SSH helper is intended for the default
localhost NAT forwarding. Optional localhost port 2323 is reserved for
telnet forwarding, but no telnet setup is required; use SSH.

8. Set up your own SSH key
--------------------------

On the host, generate a new key in the ignored private state directory.
Choose your own passphrase. Only the public key is copied into AIX.

.. code-block:: sh

   ssh-keygen -t ed25519 -f "$RUN_DIR/aix_ed25519" -C aix73-local
   cat "$RUN_DIR/aix_ed25519.pub"

At the AIX root console, create the authorized-keys file and paste your
own public key in place of the placeholder:

.. code-block:: sh

   umask 077
   mkdir -p "$HOME/.ssh"
   cat >> "$HOME/.ssh/authorized_keys" <<'PUBLIC_KEY'
   PASTE_YOUR_OWN_PUBLIC_KEY_HERE
   PUBLIC_KEY
   chmod 700 "$HOME/.ssh"
   chmod 600 "$HOME/.ssh/authorized_keys"
   lssrc -s sshd
   # If sshd is not active, start it:
   startsrc -s sshd

If this installation did not include OpenSSH, install its AIX fileset
from your appropriate licensed media before this step. Review SSH's host-key
fingerprint on first connection. The helper uses a private known-hosts file
instead of changing your normal host SSH configuration.

.. code-block:: sh

   # Back on the host:
   ./contrib/aix73/ssh-aix.sh
   # Explicit equivalent:
   ssh -i "$RUN_DIR/aix_ed25519" -o IdentitiesOnly=yes \
     -o UserKnownHostsFile="$RUN_DIR/ssh_known_hosts" -p 2222 root@127.0.0.1

``SSH_USER``, ``SSH_KEY`` and ``SSH_PORT`` customize the helper. No key,
password or populated known-hosts file is included in the project.

For interactive file transfers, run ``./contrib/aix73/sftp-aix.sh`` on the
host. It uses the same ``RUN_DIR``, ``SSH_KEY``, ``SSH_USER`` and ``SSH_PORT``
settings. SFTP uses uppercase ``-P`` for its port. Within SFTP, ``put`` uploads,
``get`` downloads and ``bye`` disconnects.

9. Enable the final native-PAPR profile and ASO
-----------------------------------------------

Shut down the bootstrap guest cleanly, then start the default profile on
the host. This selects POWER9/XICS, four vCPUs across two sockets, two memory
nodes, the stable SCSI identity and the native-PAPR compatibility additions.

.. code-block:: sh

   # Inside AIX:
   shutdown -Fh
   # Wait for 'Halt completed' and for QEMU to exit.

   # On the host, with DISK and RUN_DIR still exported:
   DAEMONIZE=1 CONSOLE=sock ./contrib/aix73/run-aix.sh
   ./contrib/aix73/ssh-aix.sh

Changing from the bootstrap QEMU mode can change AIX's device identity
and cause the boot disk to appear as ``hdisk1`` instead of ``hdisk0``.
Use ``bootinfo -b`` and ``lspath`` to inspect the actual device. Do not
hardcode a disk name into AIX's boot script.

.. code-block:: sh

   # Inside the native-PAPR guest:
   oslevel -s
   bootinfo -b
   lspath
   lssrad -av
   lparstat -i
   lssrc -s aso
   asoo -a
   tail -20 /var/log/aso/aso.log

If ASO was previously disabled, re-enable its normal service configuration
inside this native-PAPR guest, and start it if not already active:

.. code-block:: sh

   chitab 'aso:23456789:once:/usr/bin/startsrc -s aso'
   startsrc -s aso
   asoo -p -o aso_active=1

The reference topology showed two SRADs with CPUs 0-1 and 2-3. ASO remained
active and registered/monitored workloads. Its large-page-promotion message
about insufficient memory is expected at 4 GiB. Eligibility and workload
activity still govern individual optimizations; an active daemon does not
guarantee a performance gain under TCG.

10. Attach and mount the AIX Toolbox ISO
----------------------------------------

Use the Toolbox binary image for your AIX release. The source-code image
is useful for source packages, but does not replace the binary installation
media. The launcher always creates a CD drive because the virtual SCSI bus
cannot hot-add a new drive. With that drive present, media can be changed
while the VM is running.

.. code-block:: sh

   # On the host:
   export TOOLBOX_ISO="/absolute/path/to/your/Toolbox_binary.iso"
   python3 contrib/aix73/vmctl.py hmp "change cd0 \"$TOOLBOX_ISO\" raw"
   printf '%s\n' "$TOOLBOX_ISO" > "$RUN_DIR/cdrom.path"

If another disc is mounted in AIX, unmount it before changing the media.
The remembered path is private local configuration, not a tracked file.
``CDROM=/absolute/path/to/image.iso`` overrides it at cold start;
``CDROM=''`` selects an empty drive.

.. code-block:: sh

   # Inside AIX:
   cfgmgr -l vscsi0
   lsdev -Cc cdrom
   mkdir -p /mnt/toolbox
   mount -v udfs -o ro /dev/cd0 /mnt/toolbox
   ls /mnt/toolbox
   ls /mnt/toolbox/ezinstall/ppc/dnf_aixtoolbox_local.sh

The tested Toolbox image uses UDF, not cdrfs. Check your media format
if another image differs. The guest mount is not made automatic: remount
it after reboot when using the ISO repositories. To eject or replace it,
first run ``umount /mnt/toolbox`` inside AIX.

11. Install DNF and the yum command from the ISO
------------------------------------------------

IBM recommends DNF for AIX Toolbox package management. The tested local
media installer also supplies the yum 4 compatibility command. Small initial
AIX filesystems need more room: the installer requires over 512 MiB free in
both /opt and /tmp, and package caching uses /var. Check rootvg free space
before growing filesystems; the following target sizes are for a fresh
installation with smaller filesystems. Never reduce an already larger one.

.. code-block:: sh

   # Inside AIX as root:
   lsvg rootvg
   df -m /opt /tmp /var
   # Grow only when the existing filesystem is smaller than the target:
   chfs -a size=4G /opt
   chfs -a size=1G /tmp
   chfs -a size=1G /var
   /mnt/toolbox/ezinstall/ppc/dnf_aixtoolbox_local.sh /mnt/toolbox
   rpm --import /opt/freeware/etc/dnf/RPM-GPG-KEY-IBM-AIX-Toolbox
   /opt/freeware/bin/yum --version
   /opt/freeware/bin/dnf repolist
   /opt/freeware/bin/yum check

The optional project helper performs the same fresh-install setup and only
grows filesystems when needed. Run it through the established SSH connection:
``./contrib/aix73/ssh-aix.sh 'ksh -s -- /mnt/toolbox' < contrib/aix73/install-toolbox.sh``.
Set ``RESIZE_FILESYSTEMS=0`` inside the guest invocation to manage sizes yourself.
If DNF already exists, the helper leaves its repository configuration intact.

The reference ISO installed yum/DNF 4.2.17 and configured local generic,
noarch and AIX 7.3 repositories with package-signature checking enabled.
Keep the ISO mounted to install from those repositories. Select packages
instead of trying to install the entire collection at once.

.. code-block:: sh

   /opt/freeware/bin/yum list available bash
   # Example optional developer packages:
   /opt/freeware/bin/yum install bash gcc gcc-c++ make git

For new root login shells, append the Toolbox directory after native AIX
utilities in ``/.profile``. The project Toolbox helper does this automatically.
For non-login SSH commands, using the absolute executable path is reliable.
Do not set a global LIBPATH merely to make Toolbox applications run.

.. code-block:: sh

   case ":$PATH:" in
       *:/opt/freeware/bin:*) ;;
       *) PATH="$PATH:/opt/freeware/bin"; export PATH ;;
   esac

12. Boot, reboot and shut down from the shell
---------------------------------------------

Package installation needs root. If yum or dnf reports permission denied
for /var/cache/dnf/expired_repos.json, run ``id`` and use ``su -`` to enter a
root login shell before installing packages. Keep the package cache protected.
For example, root can run ``/opt/freeware/bin/dnf install rust.ppc cargo.ppc``.
AIX includes ``topas`` for live system monitoring; a command named ``top``
is not installed by default.

.. code-block:: sh

   # Host: cold boot an existing installed disk
   export DISK="/absolute/path/to/your/aix.qcow2"
   export RUN_DIR="$PWD/run-aix73"
   DAEMONIZE=1 CONSOLE=sock ./contrib/aix73/run-aix.sh

   # Host: inspect state and log in
   python3 contrib/aix73/vmctl.py qmp query-status
   ./contrib/aix73/ssh-aix.sh

   # Host: ask AIX for a clean reboot
   ./contrib/aix73/ssh-aix.sh 'shutdown -Fr'

   # Host: clean shutdown; wait for Halt completed
   ./contrib/aix73/ssh-aix.sh 'shutdown -Fh'
   tail -f "$RUN_DIR/console.log"

Do not start a second writer against the same disk. Prefer guest shutdown
over killing QEMU. Monitor ``quit`` is a recovery/finished-install tool, not
a substitute for flushing a running operating system. Before an experiment,
shut down and make a backup or an offline qcow2 snapshot on your own storage.

.. code-block:: sh

   # Only while the VM is stopped:
   dist/bin/qemu-img snapshot -c before-experiment "$DISK"
   dist/bin/qemu-img check "$DISK"

On macOS, daemon mode launches a detached ``caffeinate -im -w PID`` helper.
It inhibits host and disk idle sleep only while that QEMU process exists.
The state directory also stores the console, monitor sockets and logs.

Keep external storage connected while the VM is running. Disconnecting a
drive containing the disk image can leave QEMU with failed I/O even after
reattachment. If guest shutdown is no longer possible, stop QEMU with
``python3 contrib/aix73/vmctl.py qmp quit``, check the image offline, and
start it again. Monitor quit is a forced stop and can lose pending writes;
do not run image checks or repair tools while QEMU still has the disk open.

13. What was fixed
------------------

* Boot-platform identification: the AIX loader rejects stock qemu,pseries. The diagnostic profile exposes its recognized qemu,pseriesNOPE string; the final profile uses native PAPR identification with IBM,pSeries.
* Real-mode addressing: AIX relies on a 1 TiB VRMA segment wrap. The opt-in CPU handling masks the real-mode address to its 40-bit segment offset.
* Interrupt setup: XICS avoids the observed XIVE initialization failure. Native AIX also requires a reg property on the XICS device-tree node.
* Stable disk identity: standard SCSI INQUIRY vendor bytes and a T10 VPD 0x83 identifier let AIX restore its MPIO path and find its boot disk. The x-aix-vscsi-id property is opt-in; keep the chosen DISK_ID stable for that disk and use distinct IDs for different disks.
* Native discovery: AIX ignores an all-zero REPORT LUNS entry. The native-PAPR profile reports logical-unit addressing for target zero, matching SLOF.
* Data integrity: vSCSI's descriptor cursor was uint16_t. A 128 KiB DMA callback wrapped it to zero, so a 256 KiB request overwrote or repeated its first half. Widening it to uint32_t fixed the corrupted metadata read behind LED 0552. This is a generic SCSI correctness fix, not an AIX-only workaround.
* ASO discovery: the CPU device tree now describes the emulated DSCR controls through ibm,pa-optimizations. Native PAPR also supplies H_GET_PPP processor-capacity information and uses the correct capacity units.
* Enhanced affinity: AIX requires the CPU leaf in ibm,max-associativity-domains. The native multi-node profile includes five levels and the full interrupt-server-number range; otherwise early boot asserts on a five-versus-four mismatch.
* Firmware loading: the local SLOF recipe increases the PREP load limit so the complete AIX boot image is read.
* Diagnostics: optional hypercall, DMA-header and disk-error trace events help identify failures without modifying guest binaries.

Most compatibility behavior is opt-in through ``aix-compat``, ``aix-papr``
and ``x-aix-vscsi-id``. Default upstream-style behavior is preserved where
appropriate; the descriptor-width fix corrects the general vSCSI path.
The final installation used the original AIX boot script, kernel,
applications and fsck tools.

14. Verify the build and the guest
----------------------------------

These regression tests need no AIX media or licensed guest binaries.
They launch a tiny kernel-free POWER guest, issue real hypercalls and CRQs,
and verify data through the actual vSCSI DMA path. The NUMA test also checks
the device tree with sparse interrupt-server IDs.

.. code-block:: sh

   python3 contrib/aix73/test-vscsi-large-io.py
   python3 contrib/aix73/test-vscsi-large-io.py --aix-papr
   python3 contrib/aix73/test-vscsi-large-io.py --numa
   python3 contrib/aix73/test-vscsi-large-io.py --aix-papr --numa
   python3 contrib/aix73/test-vscsi-large-io.py \
     --qemu "$PWD/dist-debug/bin/qemu-system-ppc64" --aix-papr --numa

   ninja -C build tests/qtest/qos-test
   QTEST_QEMU_BINARY="$PWD/dist/bin/qemu-system-ppc64" \
     build/tests/qtest/qos-test \
     -p /ppc64/pseries/spapr-pci-host-bridge/pci-bus-spapr/pci-bus/virtio-scsi-pci/virtio-scsi/virtio-scsi-tests

The reference setup passed the default/native and NUMA variants, the
debug-build native NUMA case, seven virtio-scsi qtests, clean AIX reboot,
SSH/network/DNS checks and multi-hour operation with ASO active. The original
private runtime logs are deliberately not distributed.

Inside AIX, a small integrity check can use a different pattern in each
128 KiB chunk. A repeating identical chunk would hide the original DMA bug.

.. code-block:: sh

   perl -e 'for $i (0..31) { print pack("N", $i) x 32768; }' \
     > /var/tmp/aix73-io-test.bin
   cp /var/tmp/aix73-io-test.bin /tmp/aix73-io-test-copy.bin
   sync
   cmp /var/tmp/aix73-io-test.bin /tmp/aix73-io-test-copy.bin
   cksum /var/tmp/aix73-io-test.bin
   # Expected: 1119666347 4194304
   # Check the same file again after a clean reboot.

15. Troubleshooting and limits
------------------------------

* An unsupported-configuration message at CD boot usually means the patched machine options or the intended QEMU executable are not being used. Check the installed dist executable, not only the build directory.
* LED 0554 with no usable disk path calls for checking inquiry identification, REPORT LUNS and the actual boot device. Do not force hdisk0 into rc.boot.
* LED 0552 with ondisk_vgda_size is 0 can indicate the old descriptor-offset bug. Run the distinct-data regression instead of assuming the guest disk is corrupt.
* A kernel stop during interrupt setup can mean XIVE was selected or the XICS reg property is absent. The validated profile uses XICS.
* ASO's KVM rejection requires the native-PAPR profile. DSCR ENOTSUP/assertion failures call for checking CPU optimization metadata. Enhanced-affinity rejection calls for checking the NUMA configuration and associativity-domain patch.
* Large-page promotion may hibernate with 4 GiB RAM, and idle workloads may not be eligible for tuning. Some optional hypercalls and hardware-diagnostics utilities remain unsupported. Do not equate service startup with full PowerVM or physical-cache emulation.
* During verbose debugging, keep the console reader draining output. Only one socket client can be attached at a time.
* If storage I/O fails, capture QMP block counters and scsi_disk_rw_error events, stop the guest safely, and inspect the image offline. One earlier long-idle run had a transient I/O incident whose exact cause was not proven; later checks after reopening and applying the fixes passed. Keep host/disk sleep inhibition and backups rather than claiming exhaustive reliability.

.. code-block:: sh

   python3 contrib/aix73/vmctl.py hmp 'info registers'
   python3 contrib/aix73/vmctl.py qmp query-blockstats
   python3 contrib/aix73/vmctl.py hmp "dumpdtb $RUN_DIR/guest.dtb"
   dtc -I dtb -O dts "$RUN_DIR/guest.dtb"
   # To capture every hypercall temporarily (very verbose):
   python3 contrib/aix73/vmctl.py hmp 'trace-event spapr_hcall on'
   python3 contrib/aix73/vmctl.py hmp 'trace-event spapr_hcall off'

Guest GDB uses big-endian ``powerpc:common64`` on localhost:1234.
``GDB_WAIT=1`` stops CPUs at startup. ``aix.gdb`` and the CI, SLB, vector,
MSR and NUMA tracing scripts are included as source. Their absolute guest
addresses depend on the AIX build and must be verified before use on another
release. HMP dump filenames should be absolute because QEMU daemonizes.
Logs, device trees and memory dumps can contain sensitive or licensed data;
keep them outside publication commits.

Sources and publication notes
-----------------------------

* QEMU build documentation: https://www.qemu.org/docs/master/about/build-platforms.html
* SLOF build procedure: the pinned roms/SLOF/README and the public SLOF project at https://gitlab.com/qemu-project/SLOF
* IBM Toolbox getting started: https://www.ibm.com/support/pages/aix-toolbox-open-source-software-get-started
* IBM local DNF media procedure: https://community.ibm.com/community/user/blogs/sangamesh-mallayya1/2022/02/09/creating-local-repo-with-dnf-and-aix-toolbox-media

All credentials and path choices in this guide must be supplied by the
reader. Do not publish a configured state directory, media image, guest disk,
SSH key, root password, extracted kernel or diagnostic dump. Review the
staged paths and binary-file report before publishing source changes.
The README preserves upstream QEMU information below; the article draft in
wordpress.txt is HTML suitable for WordPress code view or a Custom HTML block.
Publish the source branch and verify its URL before publishing the article.

Upstream QEMU information
=========================

QEMU is a generic and open source machine & userspace emulator and
virtualizer.

QEMU is capable of emulating a complete machine in software without any
need for hardware virtualization support. By using dynamic translation,
it achieves very good performance. QEMU can also integrate with the Xen
and KVM hypervisors to provide emulated hardware while allowing the
hypervisor to manage the CPU. With hypervisor support, QEMU can achieve
near native performance for CPUs. When QEMU emulates CPUs directly it is
capable of running operating systems made for one machine (e.g. an ARMv7
board) on a different machine (e.g. an x86_64 PC board).

QEMU is also capable of providing userspace API virtualization for Linux
and BSD kernel interfaces. This allows binaries compiled against one
architecture ABI (e.g. the Linux PPC64 ABI) to be run on a host using a
different architecture ABI (e.g. the Linux x86_64 ABI). This does not
involve any hardware emulation, simply CPU and syscall emulation.

QEMU aims to fit into a variety of use cases. It can be invoked directly
by users wishing to have full control over its behaviour and settings.
It also aims to facilitate integration into higher level management
layers, by providing a stable command line interface and monitor API.
It is commonly invoked indirectly via the libvirt library when using
open source applications such as oVirt, OpenStack and virt-manager.

QEMU as a whole is released under the GNU General Public License,
version 2. For full licensing details, consult the LICENSE file.


Documentation
=============

Documentation can be found hosted online at
`<https://www.qemu.org/documentation/>`_. The documentation for the
current development version that is available at
`<https://www.qemu.org/docs/master/>`_ is generated from the ``docs/``
folder in the source tree, and is built by `Sphinx
<https://www.sphinx-doc.org/en/master/>`_.


Building
========

QEMU is multi-platform software intended to be buildable on all modern
Linux platforms, OS-X, Win32 (via the Mingw64 toolchain) and a variety
of other UNIX targets. The simple steps to build QEMU are:


.. code-block:: shell

  mkdir build
  cd build
  ../configure
  make

Additional information can also be found online via the QEMU website:

* `<https://wiki.qemu.org/Hosts/Linux>`_
* `<https://wiki.qemu.org/Hosts/Mac>`_
* `<https://wiki.qemu.org/Hosts/W32>`_


Submitting patches
==================

The QEMU source code is maintained under the GIT version control system.

.. code-block:: shell

   git clone https://gitlab.com/qemu-project/qemu.git

When submitting patches, one common approach is to use 'git
format-patch' and/or 'git send-email' to format & send the mail to the
qemu-devel@nongnu.org mailing list. All patches submitted must contain
a 'Signed-off-by' line from the author. Patches should follow the
guidelines set out in the `style section
<https://www.qemu.org/docs/master/devel/style.html>`_ of
the Developers Guide.

Additional information on submitting patches can be found online via
the QEMU website:

* `<https://wiki.qemu.org/Contribute/SubmitAPatch>`_
* `<https://wiki.qemu.org/Contribute/TrivialPatches>`_

The QEMU website is also maintained under source control.

.. code-block:: shell

  git clone https://gitlab.com/qemu-project/qemu-web.git

* `<https://www.qemu.org/2017/02/04/the-new-qemu-website-is-up/>`_

A 'git-publish' utility was created to make above process less
cumbersome, and is highly recommended for making regular contributions,
or even just for sending consecutive patch series revisions. It also
requires a working 'git send-email' setup, and by default doesn't
automate everything, so you may want to go through the above steps
manually for once.

For installation instructions, please go to:

*  `<https://github.com/stefanha/git-publish>`_

The workflow with 'git-publish' is:

.. code-block:: shell

  $ git checkout master -b my-feature
  $ # work on new commits, add your 'Signed-off-by' lines to each
  $ git publish

Your patch series will be sent and tagged as my-feature-v1 if you need to refer
back to it in the future.

Sending v2:

.. code-block:: shell

  $ git checkout my-feature # same topic branch
  $ # making changes to the commits (using 'git rebase', for example)
  $ git publish

Your patch series will be sent with 'v2' tag in the subject and the git tip
will be tagged as my-feature-v2.

Bug reporting
=============

The QEMU project uses GitLab issues to track bugs. Bugs
found when running code built from QEMU git or upstream released sources
should be reported via:

* `<https://gitlab.com/qemu-project/qemu/-/issues>`_

If using QEMU via an operating system vendor pre-built binary package, it
is preferable to report bugs to the vendor's own bug tracker first. If
the bug is also known to affect latest upstream code, it can also be
reported via GitLab.

For additional information on bug reporting consult:

* `<https://wiki.qemu.org/Contribute/ReportABug>`_


ChangeLog
=========

For version history and release notes, please visit
`<https://wiki.qemu.org/ChangeLog/>`_ or look at the git history for
more detailed information.


Contact
=======

The QEMU community can be contacted in a number of ways, with the two
main methods being email and IRC:

* `<mailto:qemu-devel@nongnu.org>`_
* `<https://lists.nongnu.org/mailman/listinfo/qemu-devel>`_
* #qemu on irc.oftc.net

Information on additional methods of contacting the community can be
found online via the QEMU website:

* `<https://wiki.qemu.org/Contribute/StartHere>`_
