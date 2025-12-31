# 📱 Quick Start: Get Briefing on iPhone

## ⚡ 3-Minute Setup (Recommended)

### Step 1: Install ntfy App (2 minutes)
1. Open **App Store** on iPhone
2. Search for **"ntfy"**
3. Install the free app
4. Open ntfy app
5. Tap **"+"** button
6. Enter topic: `milton-briefing-yourname` (make it unique!)
7. Tap **"Subscribe"**

### Step 2: Configure Auto-Send (1 minute)
On your computer:
```bash
cd ~/milton
./scripts/setup_phone_delivery.sh
```

Enter your topic name when prompted (e.g., `milton-briefing-yourname`)

### Step 3: Test It!
```bash
./scripts/send_briefing_to_phone.py --method ntfy
```

**Check your iPhone** - you should see a notification! 🎉

---

## ✅ That's It!

Your morning briefing will automatically be sent to your iPhone every day at **8:00 AM**.

### What You'll Receive:
- Weather conditions
- AI benchmark performance
- System status
- Memory vector counts

---

## 🔧 Alternative: SSH Access

If you prefer to manually fetch the briefing via SSH:

### Install Termius on iPhone
1. Download **Termius** from App Store (free)
2. Add new host:
   - Hostname: `[your computer's IP]`
   - Username: `cole-hanan`
   - Password/Key: [your credentials]

### Get Computer IP:
```bash
hostname -I | awk '{print $1}'
```

### Connect and Run:
```bash
~/bin/briefing
```

---

## 📋 Quick Commands Reference

```bash
# View briefing on computer
~/bin/briefing

# Or full path
./scripts/send_briefing_to_phone.py --method print

# Send push notification to iPhone
./scripts/send_briefing_to_phone.py --method ntfy

# Send with custom topic
./scripts/send_briefing_to_phone.py --method ntfy --topic your-topic

# Test notification
curl -d "Test from Milton!" ntfy.sh/your-topic
```

---

## 🔔 iOS Shortcuts (Advanced)

Want to trigger the briefing when you dismiss your alarm?

See full guide: [IPHONE_BRIEFING_SETUP.md](IPHONE_BRIEFING_SETUP.md)

---

## ❓ Troubleshooting

**No notification on iPhone?**
- Make sure ntfy app has notifications enabled in iPhone Settings
- Check you're subscribed to the correct topic in ntfy app
- Test with: `curl -d "Test" ntfy.sh/your-topic`

**Notification not sending automatically?**
```bash
# Check timer status
systemctl --user list-timers milton*

# View logs
journalctl --user -u milton-morning-briefing.service -n 20

# Run manually now
systemctl --user start milton-morning-briefing.service
```

**Want to change the time?**
```bash
nano ~/.config/systemd/user/milton-morning-briefing.timer
# Change: OnCalendar=*-*-* 08:00:00
systemctl --user daemon-reload
systemctl --user restart milton-morning-briefing.timer
```

---

## 🎯 Full Documentation

- [IPHONE_BRIEFING_SETUP.md](IPHONE_BRIEFING_SETUP.md) - Complete setup guide
- [MORNING_BRIEFING_GUIDE.md](MORNING_BRIEFING_GUIDE.md) - Briefing system docs

---

**Enjoy your morning briefings! ☀️**
