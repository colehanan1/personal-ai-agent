# Milton Morning Briefing Guide

## ✅ Your Morning Briefing is Set Up!

Your enhanced morning briefing automatically runs every day at **8:00 AM** and includes:
- 📍 **Weather** - Current conditions, temperature, and forecast
- 🧪 **AI Benchmark Results** - Your latest benchmark test performance
- 🖥️ **System Status** - Memory vectors and system health

## 📍 Where to Find It

**Primary Location (default):**
```
~/.local/state/milton/inbox/morning/YYYY-MM-DD.md
```

This Markdown file is updated daily at 8 AM and contains:
- Complete weather data
- Benchmark summaries and recent test queries
- System status with memory vector counts

## 🚀 Quick Commands

### View the Briefing
```bash
# Human-readable console output
./scripts/enhanced_morning_briefing.py

# View briefing Markdown
cat ~/.local/state/milton/inbox/morning/YYYY-MM-DD.md
```

### Manage the Timer
```bash
# Check when next briefing will run
systemctl --user list-timers milton*

# Run briefing now (don't wait until 8 AM)
systemctl --user start milton-morning-briefing.service

# View recent logs
journalctl --user -u milton-morning-briefing.service -n 50

# Disable automatic briefings
systemctl --user disable milton-morning-briefing.timer

# Re-enable automatic briefings
systemctl --user enable milton-morning-briefing.timer
systemctl --user start milton-morning-briefing.timer
```

## 📊 What's Included

### Weather Section
- Location: St. Louis, US
- Current temperature and conditions
- High/low forecast
- Humidity percentage

### Benchmark Performance
- Latest benchmark summary (e.g., "6/6 queries successful")
- Total number of test queries stored in memory
- Preview of recent benchmark questions and responses
- Breakdown by agent (NEXUS, CORTEX, FRONTIER)

### System Status
- Total memory vectors stored in Weaviate
- Online/offline status
- Last update timestamp

## 🔧 Customization

### Change the Time
Edit the timer file:
```bash
nano ~/.config/systemd/user/milton-morning-briefing.timer
```

Change this line:
```
OnCalendar=*-*-* 08:00:00
```

To your preferred time (24-hour format), then reload:
```bash
systemctl --user daemon-reload
systemctl --user restart milton-morning-briefing.timer
```

### Change the Location
The briefing location is set in your `.env` file:
```bash
WEATHER_LOCATION=St. Louis,US
```

## ✨ Next Run

Your next briefing is scheduled for:
**Tomorrow at 8:00 AM**

The timer is persistent, meaning if your computer is off at 8 AM, it will run when you next boot up.

## 🐛 Troubleshooting

### Briefing didn't run?
```bash
# Check timer status
systemctl --user status milton-morning-briefing.timer

# Check for errors
journalctl --user -u milton-morning-briefing.service --since today
```

### No weather data?
Use OPENWEATHER_API_KEY; WEATHER_API_KEY is supported for backward compatibility. Set it in your `.env` file.

### No benchmark data?
Run a benchmark test to populate memory:
```bash
./tests/quick_benchmark.py
```

## 📚 Related Scripts

- [scripts/enhanced_morning_briefing.py](scripts/enhanced_morning_briefing.py) - Main briefing generator
- [scripts/view_benchmark_results.py](scripts/view_benchmark_results.py) - View detailed benchmark history
- [scripts/show_benchmark_summary.sh](scripts/show_benchmark_summary.sh) - Quick benchmark summary
- [tests/quick_benchmark.py](tests/quick_benchmark.py) - Run new benchmarks

---

**Enjoy your daily morning briefings! ☀️**
