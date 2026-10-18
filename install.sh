#!/bin/sh
set -eu
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo 'Install Python: brew install python' >&2; exit 1; }
python3 build.py
prefix=${PREFIX:-"$HOME/.local"}
mkdir -p "$prefix/lib/gamepad-bridge" "$prefix/bin"
for file in startup-service.py video_stream.py audio_stream.py input_report.py mac-capture audio-capture; do
    install -m 755 "$file" "$prefix/lib/gamepad-bridge/$file"
done
cat > "$prefix/bin/gamepad-bridge" <<EOF
#!/bin/sh
exec python3 "$prefix/lib/gamepad-bridge/startup-service.py" "\$@"
EOF
chmod 755 "$prefix/bin/gamepad-bridge"
printf 'Installed: %s/bin/gamepad-bridge\n' "$prefix"
