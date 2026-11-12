#!/bin/sh
# Install the Ollama service guard (user systemd unit, no root needed) and restart Ollama.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/ollama/bin"
install -m 755 "$HERE/banana-ollama-gpu-wake.sh" "$HERE/banana-ollama-gpu-check.sh" "$BIN/"
mkdir -p "$HOME/.config/systemd/user/ollama.service.d"
install -m 644 "$HERE/banana.conf" "$HOME/.config/systemd/user/ollama.service.d/banana.conf"
systemctl --user daemon-reload
systemctl --user restart ollama
journalctl --user -u ollama -n 30 --no-pager -o cat | grep -E "banana-gpu|inference compute" || true
