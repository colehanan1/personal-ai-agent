# Milton Dashboard - Quick Start Guide

Get the dashboard running in 60 seconds.

## Prerequisites

- Node.js 18+ installed
- Milton backend running at `http://localhost:8001`

## Installation (30 seconds)

```bash
cd /home/cole-hanan/milton/milton-dashboard
npm install
```

## Start Dev Server (10 seconds)

```bash
npm run dev
```

Open browser to: **http://localhost:3000**

## First Query (20 seconds)

1. Type in the left panel: `What papers changed this week?`
2. Select agent: `Auto` (default)
3. Click **Send** or press `Cmd+Enter`
4. Watch the response stream in the center panel
5. Monitor system health in the right panel

---

## Verify Backend Connection

Before starting, ensure Milton backend is running:

```bash
# Test backend health
curl http://localhost:8001/api/system-state

# Expected output: JSON with nexus/cortex/frontier/memory status
```

If this fails, start the Milton backend first:

```bash
cd /home/cole-hanan/milton
# Start vLLM
python scripts/start_vllm.py &

# Start Weaviate
docker compose up -d

# Start backend API server (you'll need to implement this)
python scripts/start_api_server.py
```

---

## Troubleshooting

### "Connection Refused"
- Backend isn't running → Start Milton backend
- Check `.env` has correct URL

### "Blank Screen"
- Check browser console for errors
- Run `npm run lint` to check TypeScript

### "WebSocket Failed"
- Backend doesn't support WebSocket → Check backend logs
- Firewall blocking → Disable firewall temporarily

---

## What You'll See

### 3-Panel Layout

```
┌─────────────────────────────────────────────────┐
│  Milton Dashboard        [All Systems Up]       │
├────────────┬────────────────────┬───────────────┤
│            │                    │               │
│  CHAT      │  STREAM            │  DASHBOARD    │
│  (Left)    │  (Center)          │  (Right)      │
│            │                    │               │
│  • Input   │  • ROUTING (🟡)    │  • NEXUS ✓    │
│  • History │  • THINKING (🔵)   │  • CORTEX ✓   │
│            │  • TOKENS (🟢)     │  • FRONTIER ✓ │
│            │  • MEMORY (🟣)     │  • Memory ✓   │
│            │  • COMPLETE (🔵)   │               │
│            │                    │  • Metrics    │
│            │                    │  • Queue      │
└────────────┴────────────────────┴───────────────┘
```

### Color-Coded Messages

- **ROUTING** (Yellow): NEXUS decides which agent
- **THINKING** (Blue): Agent reasoning
- **TOKENS** (Green): Response streaming
- **MEMORY** (Purple): Weaviate storage
- **COMPLETE** (Teal): Summary

---

## Next Steps

1. ✅ Dashboard running at http://localhost:3000
2. ✅ Send test query
3. ✅ View live streaming
4. 📋 Export response as JSON/Markdown
5. 📊 Monitor system metrics

For detailed documentation, see [README.md](README.md).

---

**Ready to debug Phase 2!** 🚀
