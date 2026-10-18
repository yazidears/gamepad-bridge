# Router relay

The relay runs on a Linux/OpenWrt radio and forwards GamePad Ethernet frames to the Mac over UDP. It also schedules video packets next to the radio, using beacon timestamps from a monitor interface.

This is the router component, not a router provisioning tool. Use the main project instructions to set up a supported 5 GHz radio, a GamePad access point and pairing. A normal home Wi-Fi connection does not replace that radio setup.

## Build from a Mac

For the original Devolo MIPS target, run from the repository root on Apple Silicon macOS:

```sh
brew install python
python3 router/build-openwrt.py --work-dir /tmp/gamepad-router-build
```

Requires Python 3.12+, Command Line Tools, git, make and network access. The work directory must be new and contain no spaces. This fetches verified Zig 0.13 and pinned hostap/libnl sources, then builds `bin/hostapd`, `bin/hostapd_cli` and `bin/gamepad-frame-proxy` inside that directory, with license/source companions.

All three binaries were compiled and checked as static big-endian ELF32 MIPS32r2. This shortcut targets the original router ABI; it does not work for every OpenWrt router. Check your target before installing. The resulting binaries have not been tested on a fresh router. For other targets, use the matching SDK below.

## Build

On Linux, install a C compiler and Linux development headers, then run:

```sh
make
make check
sudo make install
```

The executable uses Linux packet sockets and cannot run on macOS. The media and clock tests are portable and can run on macOS with `make check`.

For OpenWrt, download the SDK matching your router's target and installed OpenWrt release. Extract it and select its target compiler:

```sh
export SDK=/path/to/openwrt-sdk
export STAGING_DIR="$SDK/staging_dir"
# Set this to the actual target compiler in your SDK, not the host compiler.
export CC="$SDK/staging_dir/toolchain-TARGET/bin/TARGET-openwrt-linux-musl-gcc"
make clean
make CC="$CC"
```

Replace both `TARGET` placeholders with the names in that SDK. Copy the resulting `frame-proxy` to the router. No cross-compiled binaries or SDK files are included here.

## Run

Create a fresh shared 32-byte token and put the same file on the Mac and router. Keep it outside the repository:

```sh
umask 077
openssl rand 32 > bridge.token
```

On the router:

```sh
sudo ./frame-proxy AP_INTERFACE /path/to/bridge.token GAMEPAD_MAC AP_MAC MAC_CLIENT_IP 0 MONITOR_INTERFACE
```

Supply the paired GamePad MAC, the emulated access-point MAC, the Mac's reachable IPv4 address and an existing radiotap monitor interface on the same radio. Use the beacon source/BSSID as the final argument if it differs from `AP_MAC`. The optional lifetime defaults to 1800 seconds; `0` keeps running until interrupted. The monitor interface defaults to `gp-clock0`.

Video needs received beacon TSF timestamps from the monitor interface. Some drivers omit these or report zero for their own transmitted beacons. The original setup used an observable same-channel beacon with a separate BSSID; pass that BSSID as the last relay argument when needed. If no valid clock arrives, the Mac waits instead of starting video. AP/monitor mode support alone does not prove this clock path works.

The relay listens on UDP 55560. Permit access only from your Mac on a trusted network: the shared token authenticates packets but traffic is unencrypted. Raw packet sockets require root or the appropriate Linux capabilities. The `192.168.1.10` and `192.168.1.11` addresses inside emitted GamePad packets belong to the emulated console link, not your home LAN.

Stop with Ctrl-C or SIGTERM. Pairing, hostapd startup, monitor-interface creation and firewall configuration are intentionally explicit setup steps; this program does not change them.

## Checks and limits

`make check` covers frame bounds, fragmentation, duplicate acknowledgments, packet flags, recovery frames and clock scheduling. It does not establish radio compatibility or replace a test on a paired GamePad. Scheduling under load can still produce visible jumps.

The wire layout follows Barista; see the project's license and attribution files.

## Fresh pairing (experimental setup recipe)

The original working setup used a Linux/OpenWrt 5 GHz radio with nl80211 AP and monitor support. Compatibility depends on driver support for the patched access point; no general router support matrix is established. The following cleaned setup recipe has not been rerun from a factory-unpaired GamePad.

Build the patched hostapd on Linux with `./build-hostap.sh`. It fetches upstream commit `d945ddd368085f255e68328f2d3b020ceea359af` and applies the included GamePad patch. Install git, make, pkg-config and libnl-3/libnl-genl-3 development headers first. For OpenWrt cross-compilation, pass SDK `CC`, `CFLAGS` and `LDFLAGS` through the environment and provide matching target libnl libraries; the native recipe is not an OpenWrt package builder. The downloaded hostap source includes its upstream `COPYING` notice; preserve it when distributing a build. The patch includes upstream Barista/DRC changes, so preserve the project attribution too.

Generate new credentials locally (the output directory must not already exist):

```sh
python3 configure.py --output /path/to/private-gamepad \
  --interface gamepad0 --ap-mac YOUR_AP_MAC --country YOUR_COUNTRY --channel YOUR_CHANNEL
```

Choose a valid locally administered unicast AP MAC and a legal 5 GHz channel for your country. Transfer the private directory to the same absolute path on the router: the generated hostapd files reference it. Copy only `bridge.token` to the Mac. Keep all of these files out of Git.

On a dedicated radio, substitute your actual PHY and interface names:

```sh
sudo iw phy YOUR_PHY interface add gamepad0 type __ap addr YOUR_AP_MAC
sudo ip link set gamepad0 mtu 1800 up
sudo iw phy YOUR_PHY interface add gp-clock0 type monitor
sudo ip link set gp-clock0 up
sudo /path/to/hostapd /path/to/private-gamepad/pairing.conf
```

In another router terminal, activate WPS using the PIN printed by configure.py. Enter the printed four-symbol sequence on the GamePad first. The protocol uses spade=0, heart=1, diamond=2, club=3 followed by the fixed suffix 5678; this is not the normal WPS checksum:

```sh
sudo /path/to/hostapd_cli -p /path/to/private-gamepad/control -i gamepad0 wps_pin any YOUR_WPS_PIN 300
```

After pairing completes, stop the pairing hostapd and start it with `runtime.conf`. Read the paired GamePad MAC from `hostapd_cli ... all_sta`, then launch `frame-proxy` with that address and your Mac's IPv4 address as described above. Use the main Mac CLI to start the bridge.

These commands create interfaces and access-point state; they are setup instructions, not automatically executed by the installer. Stop hostapd and delete the two interfaces you created when finished. Avoid sharing the radio with an uplink on another channel.
