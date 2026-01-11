# Milton Systemd Services

This directory contains systemd service and timer units for automated benchmarking.

## Files

- `milton-autobench@.service` - Service unit for running benchmarks
- `milton-autobench@.timer` - Timer unit for scheduled execution (every 6 hours)

## Installation

To install for the current user:

```bash
# Create user systemd directory
mkdir -p ~/.config/systemd/user

# Copy service and timer files
cp systemd/milton-autobench@.service ~/.config/systemd/user/
cp systemd/milton-autobench@.timer ~/.config/systemd/user/

# Reload systemd
systemctl --user daemon-reload

# Enable and start timer
systemctl --user enable milton-autobench@$USER.timer
systemctl --user start milton-autobench@$USER.timer
```

## Usage

### Check timer status
```bash
systemctl --user status milton-autobench@$USER.timer
systemctl --user list-timers
```

### Run benchmark manually
```bash
systemctl --user start milton-autobench@$USER.service
```

### View logs
```bash
journalctl --user -u milton-autobench@$USER.service -f
```

### Stop and disable
```bash
systemctl --user stop milton-autobench@$USER.timer
systemctl --user disable milton-autobench@$USER.timer
```

## Configuration

### Schedule

The default schedule runs benchmarks every 6 hours. To change this, edit the `OnCalendar` line in the timer file:

- `hourly` - Every hour
- `daily` - Every day at midnight
- `00/6:00:00` - Every 6 hours (00:00, 06:00, 12:00, 18:00)
- `Mon 10:00` - Every Monday at 10:00 AM

### Resource Limits

The service file includes resource limits:
- `MemoryMax=8G` - Maximum 8GB RAM
- `CPUQuota=400%` - Maximum 4 CPU cores

Adjust these based on your system resources.

## Security

The service includes security hardening:
- `NoNewPrivileges=true` - Cannot gain new privileges
- `PrivateTmp=true` - Private /tmp directory
- `ProtectSystem=strict` - Read-only system directories
- `ProtectHome=read-only` - Read-only home directory (except state dir)

## Troubleshooting

If the timer doesn't run:

1. Check timer is active:
   ```bash
   systemctl --user is-active milton-autobench@$USER.timer
   ```

2. Check for errors:
   ```bash
   journalctl --user -u milton-autobench@$USER.timer --since today
   ```

3. Test service manually:
   ```bash
   systemctl --user start milton-autobench@$USER.service
   journalctl --user -u milton-autobench@$USER.service -f
   ```

4. Verify paths in service file match your installation

5. Ensure user has lingering enabled (to run when not logged in):
   ```bash
   loginctl enable-linger $USER
   ```
