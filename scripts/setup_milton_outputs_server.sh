#!/bin/bash
# Milton Outputs Web Server Setup Script
#
# This script sets up a persistent, Tailscale-only Nginx server
# to browse and download files from the milton_outputs directory.
#
# Requirements:
#   - Ubuntu 24.04
#   - Tailscale installed and running
#   - sudo privileges
#
# Usage:
#   sudo ./scripts/setup_milton_outputs_server.sh

set -euo pipefail

# Configuration
TAILSCALE_IP="100.117.64.117"
PORT="8090"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUTS_DIR="${REPO_DIR}/milton_outputs"
NGINX_SITE_NAME="milton_outputs"
NGINX_SITE_CONFIG="/etc/nginx/sites-available/${NGINX_SITE_NAME}"
NGINX_SITE_ENABLED="/etc/nginx/sites-enabled/${NGINX_SITE_NAME}"

echo "========================================="
echo "Milton Outputs Web Server Setup"
echo "========================================="
echo "Tailscale IP: ${TAILSCALE_IP}"
echo "Port: ${PORT}"
echo "Serving: ${OUTPUTS_DIR}"
echo "========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root (use sudo)"
    exit 1
fi

# Verify Tailscale is installed and running
echo "[1/6] Verifying Tailscale installation..."
if ! command -v tailscale &> /dev/null; then
    echo "ERROR: Tailscale is not installed. Please install it first."
    exit 1
fi

if ! tailscale status &> /dev/null; then
    echo "ERROR: Tailscale is not running. Please start it first."
    exit 1
fi

echo "✓ Tailscale is installed and running"
echo ""

# Verify the outputs directory exists
echo "[2/6] Verifying outputs directory..."
if [ ! -d "$OUTPUTS_DIR" ]; then
    echo "ERROR: Directory $OUTPUTS_DIR does not exist"
    exit 1
fi
echo "✓ Outputs directory exists: $OUTPUTS_DIR"
echo ""

# Install Nginx if not already installed
echo "[3/6] Installing Nginx..."
if ! command -v nginx &> /dev/null; then
    echo "Installing nginx..."
    apt-get update -qq
    apt-get install -y nginx
    echo "✓ Nginx installed"
else
    echo "✓ Nginx already installed"
fi
echo ""

# Create Nginx configuration
echo "[4/6] Creating Nginx configuration..."
cat > "$NGINX_SITE_CONFIG" << EOF
# Milton Outputs Web Server
# Serves milton_outputs directory on Tailscale network only
#
# URL: http://${TAILSCALE_IP}:${PORT}/

server {
    # Listen ONLY on the Tailscale interface
    listen ${TAILSCALE_IP}:${PORT};

    server_name milton-outputs;

    # Access restrictions - Tailscale CGNAT range only
    # This is defense-in-depth since we're already binding to Tailscale IP
    allow 100.64.0.0/10;
    deny all;

    # Root directory to serve
    root ${OUTPUTS_DIR};

    # Enable directory listing
    autoindex on;
    autoindex_exact_size off;
    autoindex_localtime on;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    location / {
        # Read-only: disable methods that could modify files
        limit_except GET HEAD {
            deny all;
        }

        # Try to serve file directly, or show directory listing
        try_files \$uri \$uri/ =404;
    }

    # Logging
    access_log /var/log/nginx/milton_outputs_access.log;
    error_log /var/log/nginx/milton_outputs_error.log;
}
EOF

echo "✓ Nginx configuration created: $NGINX_SITE_CONFIG"
echo ""

# Enable the site
echo "[5/6] Enabling Nginx site..."
if [ -L "$NGINX_SITE_ENABLED" ]; then
    echo "✓ Site already enabled"
else
    ln -s "$NGINX_SITE_CONFIG" "$NGINX_SITE_ENABLED"
    echo "✓ Site enabled"
fi
echo ""

# Test and reload Nginx
echo "[6/6] Testing and reloading Nginx..."
nginx -t
systemctl enable nginx
systemctl reload nginx
echo "✓ Nginx reloaded and enabled on boot"
echo ""

# Final status check
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
systemctl status nginx --no-pager -l
echo ""
echo "========================================="
echo "Access URL: http://${TAILSCALE_IP}:${PORT}/"
echo "========================================="
echo ""
echo "Verification commands:"
echo "  1. Check Nginx status:   systemctl status nginx"
echo "  2. Test locally:         curl -I http://${TAILSCALE_IP}:${PORT}/"
echo "  3. View logs:            tail -f /var/log/nginx/milton_outputs_*.log"
echo ""
echo "To access from your iPhone:"
echo "  Open Safari and navigate to: http://${TAILSCALE_IP}:${PORT}/"
echo ""
