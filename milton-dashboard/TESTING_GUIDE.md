# Milton Dashboard - Testing Guide

## ✅ Dashboard is Working!

The dashboard is now fully functional and displays correctly at **http://localhost:3000**.

---

## What You're Seeing

### Current Status:
- ✅ **Dashboard loads** with 3-panel layout
- ✅ **Left panel** shows query input and agent selector
- ✅ **Center panel** shows "No active stream" (correct - waiting for queries)
- ✅ **Right panel** shows system status

### The "Failed to fetch" Error

This is **EXPECTED** and means:
- The dashboard is trying to connect to the backend at `http://localhost:8001`
- There's no backend running yet (you haven't built it)
- The dashboard will keep trying to reconnect every 2 seconds

**This is NORMAL for Phase 2 debugging!**

---

## How to Test the Dashboard (With Mock Backend)

I've created a simple test backend so you can see the dashboard in action:

### Step 1: Start the Test Backend

```bash
cd /home/cole-hanan/milton/milton-dashboard

# Activate conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate milton

# Start the test backend
python test-backend.py
```

**Output:**
```
======================================================================
Milton Dashboard Test Backend
======================================================================
Starting server at http://localhost:8001
Dashboard should connect automatically
======================================================================
```

### Step 2: Refresh the Dashboard

1. Go to **http://localhost:3000** in your browser
2. The "Failed to fetch" error should disappear
3. The right panel should show **"All Systems Operational"** (green)

### Step 3: Send a Test Query

1. In the left panel, type: **"What papers changed this week?"**
2. Click **"Send"** or press `Cmd+Enter`
3. Watch the magic happen:

**You'll see:**
- 🟡 **ROUTING** message (NEXUS decides which agent)
- 🔵 **THINKING** messages (agent reasoning)
- 🟢 **TOKENS** streaming word-by-word (response content)
- 🟣 **MEMORY** update (Weaviate storage)
- 🔵 **COMPLETE** summary (tokens + duration)

---

## What the Test Backend Does

The `test-backend.py` file provides:

✅ **GET /api/system-state** - Returns mock agent status
✅ **POST /api/ask** - Accepts queries and returns request ID
✅ **WebSocket /ws/request/{id}** - Streams mock responses

It simulates a real Milton backend so you can:
- Test the dashboard UI
- See WebSocket streaming in action
- Debug the frontend without building the full backend

---

## Next Steps

### For Debugging:
The dashboard is **100% ready**. You can now:
1. Test different queries
2. See request history build up
3. Export responses as JSON/Markdown
4. Monitor system metrics

### For Production:
Replace `test-backend.py` with a real backend that:
1. Calls your actual NEXUS/CORTEX/FRONTIER agents
2. Streams real responses from vLLM
3. Stores data in Weaviate
4. Processes the job queue

---

## Troubleshooting

### "Failed to fetch" persists after starting backend
**Solution:** Check if backend is running:
```bash
curl http://localhost:8001/api/system-state
# Should return JSON with agent status
```

### Backend won't start
**Error:** `Address already in use`
**Solution:** Kill existing process on port 8001:
```bash
lsof -ti:8001 | xargs kill -9
```

### Dashboard shows blank screen
**Solution:** Check browser console (F12) for errors
- If you see TypeScript errors, run: `npm run lint`
- If Vite crashed, restart: `npm run dev`

### WebSocket not connecting
**Check:** Backend must support WebSocket at `/ws/request/{id}`
```bash
# Test WebSocket endpoint (requires wscat)
npm install -g wscat
wscat -c ws://localhost:8001/ws/request/test_123
```

---

## Backend is Currently Running

I've already started the test backend for you:
```bash
# Backend: http://localhost:8001 ✅
# Dashboard: http://localhost:3000 ✅
```

**Just refresh your browser at localhost:3000 and try sending a query!**

---

## Files Created for Testing

- **test-backend.py** - Mock backend server
- **TESTING_GUIDE.md** - This file
- **FIXES_APPLIED.md** - List of bugs that were fixed

---

## Success Indicators

When everything is working, you should see:

✅ **Left Panel:**
- Query input (functional)
- Request shows in history
- Status changes: PENDING → RUNNING → COMPLETE

✅ **Center Panel:**
- Messages appear in real-time
- Color-coded by type
- Auto-scrolls to bottom

✅ **Right Panel:**
- All 4 agents show "UP" (green)
- Current request metrics update
- Memory stats displayed

---

**Ready to test!** 🚀

Just refresh the browser and send a query like:
- "What papers changed this week?"
- "Analyze this code"
- "Run hyperparameter sweep"

The dashboard will route it to the appropriate mock agent and show you the full streaming response!
