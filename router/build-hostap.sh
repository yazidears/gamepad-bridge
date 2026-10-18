#!/bin/sh
set -eu
# Run on Linux with git, make, a C toolchain, pkg-config, and libnl-3/libnl-genl-3 development packages.
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
work=${1:-"$root/build/hostap"}
git clone https://chromium.googlesource.com/external/w1.fi/cgit/hostap "$work"
git -C "$work" checkout --detach d945ddd368085f255e68328f2d3b020ceea359af
git -C "$work" apply "$root/patches/hostap-gamepad.patch"
cat > "$work/hostapd/.config" <<'CONFIG'
CONFIG_DRIVER_NL80211=y
CONFIG_LIBNL32=y
CONFIG_EAP=y
CONFIG_WPS=y
CONFIG_IPV6=y
CONFIG_TENDONIN=y
CONFIG_TLS=internal
CONFIG_INTERNAL_LIBTOMMATH=y
CONFIG_INTERNAL_LIBTOMMATH_FAST=y
CONFIG_NO_RADIUS=y
CONFIG_NO_ACCOUNTING=y
CONFIG_NO_VLAN=y
CONFIG_IEEE80211N=y
CONFIG_DEBUG_FILE=y
CONFIG
make -C "$work/hostapd" hostapd hostapd_cli
printf 'Built in %s/hostapd. Keep upstream COPYING with redistributed binaries.\n' "$work"
