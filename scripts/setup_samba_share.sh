#!/bin/bash
set -e

echo "========================================"
echo "Milton SMB Share Setup"
echo "========================================"
echo ""

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_OUTPUT_DIR="$ROOT_DIR/shared_outputs"
OUTPUT_DIR="${OUTPUT_DIR:-$DEFAULT_OUTPUT_DIR}"
OUTPUT_SHARE_NAME="${OUTPUT_SHARE_NAME:-milton_outputs}"
HOSTNAME_VALUE="$(hostname)"

mkdir -p "$OUTPUT_DIR"

echo "Output directory: $OUTPUT_DIR"
echo "Share name: $OUTPUT_SHARE_NAME"
echo ""

if ! command -v smbd >/dev/null 2>&1; then
    echo "Samba (smbd) not found."
    echo "Install it with:"
    echo "  sudo apt-get update"
    echo "  sudo apt-get install samba"
    echo ""
else
    echo "Samba detected: $(command -v smbd)"
    echo ""
fi

SMB_CONF="/etc/samba/smb.conf"
if [ -f "$SMB_CONF" ]; then
    if grep -q "^\[$OUTPUT_SHARE_NAME\]" "$SMB_CONF"; then
        echo "Found existing share [$OUTPUT_SHARE_NAME] in $SMB_CONF"
    else
        echo "Share [$OUTPUT_SHARE_NAME] not found in $SMB_CONF"
    fi
else
    echo "Samba config not found at $SMB_CONF"
fi

echo ""
echo "Add this to /etc/samba/smb.conf (requires sudo):"
echo ""
cat <<EOF
[$OUTPUT_SHARE_NAME]
   path = $OUTPUT_DIR
   browseable = yes
   read only = yes
   guest ok = no
EOF
echo ""
echo "Set an SMB password for your user:"
echo "  sudo smbpasswd -a $USER"
echo ""
echo "Restart Samba:"
echo "  sudo systemctl restart smbd"
echo ""
echo "Set these in your .env:"
echo "  OUTPUT_DIR=$OUTPUT_DIR"
echo "  OUTPUT_SHARE_URL=smb://$HOSTNAME_VALUE/$OUTPUT_SHARE_NAME"
echo ""
echo "iPhone Files app > Connect to Server:"
echo "  smb://$HOSTNAME_VALUE/$OUTPUT_SHARE_NAME"
echo ""
