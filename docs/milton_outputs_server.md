# Milton Outputs Web Server

A persistent, secure (Tailscale-only) web endpoint for browsing and downloading files from Milton's output directory.

## Overview

This server provides read-only access to the `milton_outputs` directory (symlinked to `shared_outputs`) over your Tailscale network. It uses Nginx for reliability and persistence across reboots.

**Key Features:**
- 🔒 **Tailscale-only access** - Not exposed to the public internet
- 📁 **Directory listing** - Browse files with autoindex
- ✅ **Read-only** - GET/HEAD requests only, no modifications
- 🔄 **Persistent** - Survives reboots (systemd-managed)
- 📱 **Mobile-friendly** - Access from your iPhone/iPad via Tailscale

## Quick Start

### Prerequisites

- Ubuntu 24.04 (or similar Debian-based system)
- Tailscale installed and authenticated
- Tailscale IP: `100.117.64.117` (configured in setup script)
- sudo privileges

### Installation

Run the automated setup script:

```bash
sudo ./scripts/setup_milton_outputs_server.sh
```

This script will:
1. Verify Tailscale is installed and running
2. Verify the `milton_outputs` directory exists
3. Install Nginx (if not already installed)
4. Create Nginx configuration for Tailscale-only access
5. Enable the site and reload Nginx
6. Enable Nginx to start on boot

### Access URL

Once installed, access the server at:

```
http://100.117.64.117:8080/
```

This URL is accessible from any device on your Tailscale network, including your iPhone.

## Verification

After installation, verify the server is working:

```bash
# Check Nginx status
systemctl status nginx

# Test HTTP response locally
curl -I http://100.117.64.117:8080/

# View access logs
tail -f /var/log/nginx/milton_outputs_access.log

# View error logs
tail -f /var/log/nginx/milton_outputs_error.log
```

Expected output from `curl -I`:
```
HTTP/1.1 200 OK
Server: nginx/1.24.0 (Ubuntu)
Date: ...
Content-Type: text/html
```

## Configuration

### Change Port

Edit the setup script or Nginx config manually:

```bash
# Edit setup script (recommended for reproducibility)
nano scripts/setup_milton_outputs_server.sh
# Change: PORT="8080" to desired port

# Or edit Nginx config directly
sudo nano /etc/nginx/sites-available/milton_outputs
# Change: listen 100.117.64.117:8080; to desired port
sudo nginx -t && sudo systemctl reload nginx
```

### Change Output Directory

To serve a different directory:

```bash
# Edit setup script
nano scripts/setup_milton_outputs_server.sh
# Change: OUTPUTS_DIR="${REPO_DIR}/milton_outputs"

# Or edit Nginx config directly
sudo nano /etc/nginx/sites-available/milton_outputs
# Change: root /home/cole-hanan/milton/milton_outputs;
sudo nginx -t && sudo systemctl reload nginx
```

### Change Tailscale IP

If your Tailscale IP changes:

```bash
# Edit setup script
nano scripts/setup_milton_outputs_server.sh
# Change: TAILSCALE_IP="100.117.64.117"

# Or edit Nginx config directly
sudo nano /etc/nginx/sites-available/milton_outputs
# Change: listen 100.117.64.117:8080; to new IP
sudo nginx -t && sudo systemctl reload nginx
```

## Security Notes

### Tailscale-Only Access

The server implements **defense-in-depth** security:

1. **Bind to Tailscale IP only** - Nginx listens on `100.117.64.117:8080`, not `0.0.0.0:8080`
   - This prevents access from any interface except Tailscale
   - Even if firewall rules fail, the service is not publicly exposed

2. **IP allowlist** - Nginx config includes `allow 100.64.0.0/10; deny all;`
   - Restricts access to Tailscale's CGNAT range (100.64.0.0/10)
   - Additional layer of protection

3. **Read-only** - `limit_except GET HEAD { deny all; }`
   - Only GET and HEAD HTTP methods are allowed
   - No PUT, POST, DELETE, or other modification methods

4. **Security headers** - X-Frame-Options, X-Content-Type-Options, X-XSS-Protection
   - Prevents common web vulnerabilities

### What This Protects Against

✅ Public internet access (not bound to 0.0.0.0)
✅ Unauthorized LAN access (IP allowlist)
✅ File modification/deletion (read-only)
✅ XSS attacks (security headers)

### What This Does NOT Protect Against

❌ Tailscale account compromise (attacker on your Tailnet can access)
❌ Local privilege escalation (attacker with shell access can read files anyway)

**Recommendation:** Use Tailscale ACLs to further restrict which devices can access port 8080 on this node.

## Troubleshooting

### Server Not Starting

```bash
# Check Nginx configuration syntax
sudo nginx -t

# Check Nginx error logs
sudo tail -50 /var/log/nginx/error.log

# Check systemd status
systemctl status nginx

# Restart Nginx
sudo systemctl restart nginx
```

### Can't Access from iPhone

1. Verify Tailscale is connected on both devices:
   ```bash
   # On server
   tailscale status

   # On iPhone: Open Tailscale app, ensure connected
   ```

2. Verify server is listening:
   ```bash
   sudo netstat -tlnp | grep 8080
   # Should show: tcp 0 0 100.117.64.117:8080 0.0.0.0:* LISTEN
   ```

3. Test from server:
   ```bash
   curl http://100.117.64.117:8080/
   ```

4. Check firewall rules:
   ```bash
   sudo ufw status
   # If ufw is active, add rule:
   sudo ufw allow from 100.64.0.0/10 to any port 8080
   ```

### Permission Errors

If Nginx can't read files:

```bash
# Check directory permissions
ls -la /home/cole-hanan/milton/milton_outputs

# Ensure Nginx user (www-data) can read
sudo chmod -R 755 /home/cole-hanan/milton/milton_outputs
```

### Port Already in Use

```bash
# Check what's using port 8080
sudo netstat -tlnp | grep 8080

# Change port in Nginx config
sudo nano /etc/nginx/sites-available/milton_outputs
# Change listen directive to different port
sudo nginx -t && sudo systemctl reload nginx
```

## Uninstallation

To remove the server:

```bash
# Disable and remove Nginx site
sudo rm /etc/nginx/sites-enabled/milton_outputs
sudo rm /etc/nginx/sites-available/milton_outputs
sudo systemctl reload nginx

# Optionally uninstall Nginx (if not used for other purposes)
sudo apt-get remove --purge nginx nginx-common
sudo apt-get autoremove
```

## Architecture

```
┌─────────────────┐
│  iPhone/iPad    │
│  (Safari)       │
└────────┬────────┘
         │ Tailscale VPN
         │ http://100.117.64.117:8080/
         ▼
┌─────────────────────────────────────┐
│  Milton Server                      │
│  ┌───────────────────────────────┐  │
│  │  Nginx                        │  │
│  │  - Listen: 100.117.64.117:8080│  │
│  │  - Allow: 100.64.0.0/10 only  │  │
│  │  - Root: /home/.../milton_    │  │
│  │          outputs              │  │
│  │  - Autoindex: on              │  │
│  │  - Methods: GET, HEAD only    │  │
│  └───────────────┬───────────────┘  │
│                  │                   │
│                  ▼                   │
│  ┌───────────────────────────────┐  │
│  │  milton_outputs/              │  │
│  │  (symlink -> shared_outputs/) │  │
│  │  ├── milton_req_*.txt         │  │
│  │  ├── codex_output_*.txt       │  │
│  │  └── ...                      │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

## Related Documentation

- [Milton README](../README.md) - Main project documentation
- [Phase 2 Complete](PHASE2_COMPLETE.md) - Current system status
- [Environment Variables](.env.example) - See OUTPUT_DIR configuration

## Support

For issues or questions:
- Check troubleshooting section above
- Review Nginx logs: `/var/log/nginx/milton_outputs_*.log`
- Verify Tailscale connectivity: `tailscale status`
