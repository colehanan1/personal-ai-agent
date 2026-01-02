#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${STATE_DIR:-$HOME/.local/state/milton}"
OUTPUT_DIR="${OUTPUT_DIR:-$STATE_DIR/outputs}"

echo "Using OUTPUT_DIR: ${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "ERROR: tailscale is not installed. Install it first: https://tailscale.com/download"
  exit 1
fi

if ! tailscale status >/dev/null 2>&1; then
  echo "ERROR: tailscale is not running or not logged in."
  echo "Run: tailscale up"
  exit 1
fi

status_output="$(tailscale serve status 2>&1 || true)"

if echo "${status_output}" | grep -qi "no serve config"; then
  echo "Tailscale Serve is not configured. Enabling serve for ${OUTPUT_DIR}..."
  sudo tailscale serve --bg "${OUTPUT_DIR}"
  echo ""
  echo "Serve status:"
  tailscale serve status
else
  echo "Tailscale Serve appears to be configured already."
  echo ""
  echo "${status_output}"
  echo ""
  echo "No changes made. If you want to serve OUTPUT_DIR, run:"
  echo "  sudo tailscale serve --bg \"${OUTPUT_DIR}\""
fi

echo ""
echo "Next step:"
echo "1) Find your https://<node>.<tailnet>.ts.net URL in the status output above."
echo "2) Set OUTPUT_BASE_URL in your .env to that URL (no trailing slash)."
echo "3) Do NOT enable Funnel (keep this tailnet-only)."
