#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

mkdir -p "$UNIT_DIR"
cp "$SCRIPT_DIR"/milton-*.service "$SCRIPT_DIR"/milton-*.timer "$UNIT_DIR"/

systemctl --user daemon-reload
systemctl --user enable --now \
  milton-evening-briefing.timer \
  milton-job-processor.timer \
  milton-morning-briefing.timer

echo "Installed Milton daily OS timers."
