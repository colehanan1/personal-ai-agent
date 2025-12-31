# 📱 iPhone Morning Briefing Setup Guide

Get your Milton morning briefing delivered to your iPhone automatically when you turn off your alarm!

## 🎯 Three Methods Available

### Method 1: Push Notifications (Recommended ⭐)
**Best for**: Automatic delivery, no SSH needed

### Method 2: SSH Command via iOS App
**Best for**: Quick manual checks

### Method 3: iOS Shortcuts Automation
**Best for**: Triggering on alarm dismiss

---

## 📲 Method 1: Push Notifications with ntfy.sh

**This is the easiest and most reliable method!**

### Step 1: Install ntfy App on iPhone
1. Open App Store
2. Search for "ntfy"
3. Install the free ntfy app
4. Open the app

### Step 2: Subscribe to Your Topic
1. In the ntfy app, tap the "+" button
2. Enter a topic name (e.g., `milton-briefing-cole`)
   - Make it unique! Use your name or random string
   - Example: `milton-briefing-xk7j2p`
3. Tap "Subscribe"

### Step 3: Configure on Your Computer
```bash
# Add to your .env file
echo "NTFY_TOPIC=milton-briefing-cole" >> .env
```

### Step 4: Update Morning Briefing to Auto-Send
Edit the systemd service to send notifications:
```bash
nano ~/.config/systemd/user/milton-morning-briefing.service
```

Change the `ExecStart` line to:
```
ExecStart=/bin/bash -c '/home/cole-hanan/milton/scripts/enhanced_morning_briefing.py && /home/cole-hanan/milton/scripts/send_briefing_to_phone.py --method ntfy'
```

Then reload:
```bash
systemctl --user daemon-reload
systemctl --user restart milton-morning-briefing.timer
```

### Step 5: Test It!
```bash
# Send test notification
./scripts/send_briefing_to_phone.py --method ntfy

# Or with custom topic
./scripts/send_briefing_to_phone.py --method ntfy --topic milton-briefing-cole
```

You should receive a push notification on your iPhone! 🎉

### Notification Settings
- Tap notification to expand and read full briefing
- Enable notifications for ntfy app in iPhone Settings
- Set notification sound/vibration as desired

---

## 🔐 Method 2: SSH Command (Manual)

### Step 1: Install SSH Client on iPhone
Download one of these apps:
- **Termius** (recommended - free, easy to use)
- **Blink Shell** (powerful, one-time purchase)
- **iSH** (full Linux terminal)

### Step 2: Set Up SSH Connection in App

#### In Termius:
1. Tap "Hosts" → "+"
2. Enter details:
   - Alias: Milton Server
   - Hostname: `[your computer's IP address]`
   - Username: `cole-hanan`
   - Password or SSH Key: [your credentials]
3. Save

#### Find Your Computer's IP:
```bash
hostname -I | awk '{print $1}'
```

### Step 3: Create Quick Command
In Termius, create a "Snippet":
1. Go to Snippets
2. Create new snippet called "Morning Briefing"
3. Command: `/home/cole-hanan/milton/scripts/briefing`

### Step 4: Use It
1. Open Termius
2. Connect to Milton Server
3. Run the "Morning Briefing" snippet (or type `briefing`)
4. Read your briefing!

### Even Simpler SSH Command:
After connecting via SSH, just type:
```bash
briefing
```

---

## ⚡ Method 3: iOS Shortcuts Automation

### Trigger briefing when you dismiss your alarm!

### Step 1: Enable SSH on Your Computer (if not already)
```bash
# Check if SSH is running
sudo systemctl status ssh

# If not running, install and start
sudo apt install openssh-server
sudo systemctl enable ssh
sudo systemctl start ssh
```

### Step 2: Set Up SSH Key (No Password Needed)
On your computer:
```bash
# Generate SSH key if you don't have one
ssh-keygen -t ed25519 -C "iphone-shortcuts"

# Display your private key
cat ~/.ssh/id_ed25519
```

Copy this key - you'll paste it into iOS Shortcuts.

### Step 3: Create iOS Shortcut

1. Open **Shortcuts** app on iPhone
2. Tap "+" to create new shortcut
3. Name it "Get Morning Briefing"

#### Add these actions:

**Action 1: Run Script Over SSH**
- Search for "Run Script Over SSH"
- Host: `[your computer's IP address]`
- Port: `22`
- User: `cole-hanan`
- Authentication: SSH Key
- SSH Key: [paste the private key from above]
- Script: `/home/cole-hanan/milton/scripts/send_briefing_to_phone.py --method print`

**Action 2: Show Result**
- Search for "Show Result"
- Connect to output of previous action

### Step 4: Create Automation

1. Go to "Automation" tab in Shortcuts
2. Tap "+" → "Create Personal Automation"
3. Choose **"Alarm"**
4. Select "When alarm is stopped"
5. Choose "Any" or select specific alarm
6. Tap "Next"
7. Search for and add your "Get Morning Briefing" shortcut
8. **Turn OFF "Ask Before Running"** (important!)
9. Tap "Done"

Now when you dismiss your alarm, the briefing will automatically run! 📱

---

## 🔧 Advanced: Telegram Bot (Optional)

If you prefer Telegram:

### Step 1: Create Telegram Bot
1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Send `/newbot`
3. Follow instructions to create bot
4. Save the bot token

### Step 2: Get Your Chat ID
1. Message your new bot
2. Visit: `https://api.telegram.org/bot[YOUR_BOT_TOKEN]/getUpdates`
3. Find your `chat_id` in the response

### Step 3: Configure
```bash
# Add to .env
echo "TELEGRAM_BOT_TOKEN=your_bot_token_here" >> .env
echo "TELEGRAM_CHAT_ID=your_chat_id_here" >> .env
```

### Step 4: Test
```bash
./scripts/send_briefing_to_phone.py --method telegram
```

---

## 📋 Quick Reference

### Test Commands
```bash
# Print briefing to terminal
./scripts/send_briefing_to_phone.py --method print

# Send via ntfy.sh
./scripts/send_briefing_to_phone.py --method ntfy

# Send via Telegram
./scripts/send_briefing_to_phone.py --method telegram

# Send via all configured methods
./scripts/send_briefing_to_phone.py --method all

# Quick command (just print)
./scripts/briefing
```

### Update Automatic Sending

To make briefing auto-send every morning at 8 AM:

**Edit service file:**
```bash
nano ~/.config/systemd/user/milton-morning-briefing.service
```

**Change ExecStart line to:**
```
ExecStart=/bin/bash -c '/home/cole-hanan/milton/scripts/enhanced_morning_briefing.py && /home/cole-hanan/milton/scripts/send_briefing_to_phone.py --method ntfy'
```

**Reload:**
```bash
systemctl --user daemon-reload
systemctl --user restart milton-morning-briefing.timer
```

---

## ❓ Troubleshooting

### ntfy notifications not appearing?
- Check iPhone notification settings for ntfy app
- Make sure you're subscribed to the correct topic
- Test with: `curl -d "Test message" ntfy.sh/your-topic`

### SSH connection fails?
- Verify SSH is running: `sudo systemctl status ssh`
- Check firewall allows port 22
- Verify you're on same network (or set up port forwarding)
- Try password authentication first before SSH keys

### iOS automation not running?
- Make sure "Ask Before Running" is OFF
- Check Shortcuts app has necessary permissions
- Verify SSH key is copied correctly
- Test the shortcut manually first

### Briefing data looks old?
```bash
# Regenerate briefing
./scripts/enhanced_morning_briefing.py

# Check when it last ran
systemctl --user list-timers milton*
```

---

## 🎯 Recommended Setup

**For best experience:**
1. ✅ Use **ntfy.sh** for automatic push notifications
2. ✅ Set up **SSH shortcut** in Termius for quick manual checks
3. ✅ Configure systemd to auto-send at 8 AM
4. ✅ Set up iOS alarm automation as backup

This gives you:
- Automatic delivery every morning
- Quick manual access anytime
- Alarm-triggered delivery as fallback
- No need to open computer or SSH manually

---

## 📱 What You'll Receive

Your iPhone will show:
```
☀️ MORNING BRIEFING
December 31, 2025 at 08:00 AM

📍 WEATHER
Location: St. Louis,US
Current: 36°F, Clouds
Range: 34°F - 37°F
Humidity: 74%

🧪 AI PERFORMANCE
Benchmark: 6/6 queries successful
Total queries in memory: 21

🖥️ SYSTEM STATUS
Memory vectors: 44
Status: ONLINE
```

**With links to:**
- Dashboard
- API Status
- Full briefing JSON

---

**Questions?** Check the main guide: [MORNING_BRIEFING_GUIDE.md](MORNING_BRIEFING_GUIDE.md)
