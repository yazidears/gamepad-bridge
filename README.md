# GamePad Bridge

Use a Wii U GamePad as a wireless screen for a Mac. Desktop video and system audio go to the GamePad; buttons, sticks and touch reports come back to the Mac.

This needs a separate OpenWrt radio. The Mac's built-in Wi-Fi cannot provide the GamePad access point. It's experimental: playback worked on the original hardware setup, but occasional jumps remain. A fresh installation on another router has not been tested.

## Install

Apple Silicon Mac, macOS 13 or later, and Xcode Command Line Tools:

```sh
brew tap yazidears/wiiu
brew install yazidears/wiiu/gamepad-bridge
```

Homebrew builds the capture helpers and installs the command and router setup tools.
To install from a source checkout instead, run `brew install python`, `./install.sh`,
and add `~/.local/bin` to your PATH.

## Set up the radio

Follow [router/README.md](router/README.md) to build the relay and patched hostapd, pair the GamePad, and start the temporary access point. The Homebrew install includes these tools:

```sh
gamepad-bridge-router-build --work-dir /tmp/gamepad-router-build
gamepad-bridge-pairing-config --help
```

The router build targets the original Devolo MIPS setup. Use a dedicated supported radio with an Ethernet link to the Mac. Pairing replaces the GamePad's existing console pairing; pair it with the Wii U again to return to the console.

Use your own router address, AP and GamePad MAC addresses, and relay token:

```sh
gamepad-bridge --router "$ROUTER_IP" --bind "$MAC_ETHERNET_IP" \
  --ap-mac "$AP_MAC" --gamepad-mac "$GAMEPAD_MAC" \
  --token "$HOME/.config/gamepad-bridge/relay-token.bin"
```

Grant **Screen & System Audio Recording** permission when macOS asks. Restart the command after granting access. Turn the GamePad on after the router access point is ready. Press Ctrl-C to stop the Mac sender, then stop the router session using the router instructions.

Add `--input-json` to print decoded controls. This release exposes input reports; it does not install a virtual controller or inject keyboard/mouse events. Touch uses default calibration. The built-in camera and microphone are not supported.

## Local data

The token and pairing credentials are yours; keep them outside this checkout. The sender creates private status files, a socket and metadata logs under `~/.local/state/gamepad-bridge`. It does not save desktop frames or audio. The relay uses a shared token without transport encryption, so use a trusted wired network and keep UDP 55560 off the internet.

## Development

```sh
python3 build.py --test
python3 -m unittest discover -v
```

The vendored codec includes the Apple Silicon coefficient-order correction. See [vendor/codec/UPSTREAM.md](vendor/codec/UPSTREAM.md). Tests cover codec behavior and packet formats; they do not establish radio compatibility or replace a real GamePad test.

## Credits and license

Based on [Barista](https://github.com/BetaZay/Barista), including its GamePad protocol and encoder work. Protocol research also comes from libdrc. GPL-2.0; see [LICENSE](LICENSE). Bundled codec dependencies and router dependencies retain their original notices.
