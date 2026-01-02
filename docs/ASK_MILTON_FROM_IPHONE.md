# 💬 Ask Milton Questions from Your iPhone

Your Milton AI is now listening for questions from your iPhone! Send a question and get an AI-powered response sent back to you.

## 🚀 Quick Start

### What You Need:
1. **ntfy app** installed on iPhone (free from App Store)
2. **Two topics** subscribed in ntfy:
   - `milton-briefing-code` - For receiving responses
   - `milton-briefing-code-ask` - For sending questions

### How It Works:
1. You send a question to `milton-briefing-code-ask`
2. Milton's listener service picks it up
3. Your AI processes the question
4. The answer is sent back to `milton-briefing-code`
5. You get a notification with the response!

---

## ✅ Recommended: Systemd Listener Service (Primary Path)

This repo ships a first-class systemd user unit: `systemd/milton-phone-listener.service`.

### 1) Configure Topics
Ensure `.env` includes `NTFY_TOPIC=your-topic` (responses). Questions arrive on `${NTFY_TOPIC}-ask`.

If you already run `milton-orchestrator` on the same ntfy topics, do **not** run both listeners. Either disable one service or use distinct topics to avoid duplicate responses.

### 2) Install + Enable
```bash
mkdir -p ~/.config/systemd/user
cp /home/cole-hanan/milton/systemd/milton-phone-listener.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now milton-phone-listener.service
```

### 3) Check Status + Logs
```bash
systemctl --user status milton-phone-listener
journalctl --user -u milton-phone-listener -f
```

---

## 📱 Method 1: Using ntfy App (Easiest)

### Setup (One Time):
1. Open **ntfy** app on iPhone
2. Tap **"+"** to add topics
3. Subscribe to both:
   - `milton-briefing-code` (responses)
   - `milton-briefing-code-ask` (questions)

### To Ask a Question:
1. Open **ntfy** app
2. Tap on **`milton-briefing-code-ask`**
3. Tap the **text input field** at the bottom
4. Type your question
5. Tap **Send**
6. Wait 5-30 seconds
7. Check **`milton-briefing-code`** for your answer!

**Example Questions:**
- "What is the weather?"
- "Summarize today's benchmark results"
- "Write a Python function to calculate fibonacci numbers"
- "What are the latest AI research papers?"

---

## ⚡ Method 2: iOS Shortcuts (Advanced)

Create a Shortcut to ask Milton with one tap!

### Create "Ask Milton" Shortcut:

1. Open **Shortcuts** app on iPhone
2. Tap **"+"** to create new shortcut
3. Name it "Ask Milton"

#### Add These Actions:

**Action 1: Ask for Input**
- Search for "Ask for Input"
- Prompt: "What do you want to ask Milton?"
- Input Type: Text

**Action 2: Get Contents of URL**
- URL: `https://ntfy.sh/milton-briefing-code-ask`
- Method: POST
- Request Body: Text
- Text: `[Provided Input]` (from previous action)

**Action 3: Show Notification**
- Title: "Question Sent to Milton"
- Body: "Check milton-briefing-code for response"

**Action 4: Wait** (optional)
- Wait for: 15 seconds

**Action 5: Open URL** (optional)
- URL: `ntfy://milton-briefing-code`
- This opens ntfy app to see the response

### Use It:
1. Run the "Ask Milton" shortcut
2. Type your question
3. Tap Done
4. Wait for notification with answer!

### Add to Home Screen:
1. Edit the shortcut
2. Tap the icon at top
3. Choose "Add to Home Screen"
4. Now you have a one-tap "Ask Milton" button!

---

## 🎙️ Method 3: Siri Integration

Make the Shortcut Siri-enabled:

1. Edit your "Ask Milton" shortcut
2. Tap the "i" info button
3. Tap "Add to Siri"
4. Record phrase: "Ask Milton"

**Now you can say:**
- "Hey Siri, Ask Milton"
- Siri will prompt you for your question
- Answer is sent to your ntfy notifications!

---

## 💻 Method 4: SSH from iPhone Terminal

If you have a terminal app (Termius, Blink, iSH):

### Quick Question:
```bash
ssh cole-hanan@[your-ip]
curl -d "Your question here" ntfy.sh/milton-briefing-code-ask
```

### Or use the helper script:
```bash
ssh cole-hanan@[your-ip]
~/bin/ask-milton "Your question here"
```

---

## 📊 What Happens Behind the Scenes

1. **Listener Service Running**: `milton-phone-listener.service` runs 24/7
2. **Monitoring ntfy**: Watches `milton-briefing-code-ask` for new messages
3. **AI Processing**: Sends your question to Milton API (NEXUS/CORTEX/FRONTIER)
4. **Response Delivery**: Sends answer back via `milton-briefing-code`
5. **Notification**: You get a push notification with the full answer

---

## 🔧 Service Management

### Enable at Login:
```bash
systemctl --user enable --now milton-phone-listener
```

### Check if Listener is Running:
```bash
systemctl --user status milton-phone-listener
```

### View Live Logs:
```bash
journalctl --user -u milton-phone-listener -f
```

### Restart Service:
```bash
systemctl --user restart milton-phone-listener
```

### Disable Service:
```bash
systemctl --user disable --now milton-phone-listener
```

### Stop Service:
```bash
systemctl --user stop milton-phone-listener
```

### Start Service:
```bash
systemctl --user start milton-phone-listener
```

---

## Manual Mode (Debugging)

Stop the service first to avoid running two listeners:
```bash
systemctl --user stop milton-phone-listener
```

Then run the script directly:
```bash
./scripts/ask_from_phone.py --listen
./scripts/ask_from_phone.py --ask "What is the weather?"
```

---

## Smoke Test (End-to-end)

Publish a test question and observe the response:
```bash
# Send test question
curl -d "What is 2+2?" https://ntfy.sh/${NTFY_TOPIC}-ask

# Observe response (or watch in the ntfy app)
curl -s "https://ntfy.sh/${NTFY_TOPIC}/json?poll=1" | jq -r '.message'
```
If `NTFY_TOPIC` is not exported in your shell, replace it with your topic or run `set -a; source .env; set +a`.

---

## ✅ Example Workflow

**Morning Routine:**
1. Wake up, dismiss alarm
2. Check **`milton-briefing-code`** in ntfy - see your morning briefing
3. Want to know more? Tap **`milton-briefing-code-ask`**
4. Ask: "What's in the news today about AI?"
5. Get response in 10-20 seconds
6. Continue your day informed!

**Throughout the Day:**
1. Wondering about something?
2. Say "Hey Siri, Ask Milton"
3. Ask your question
4. Get answer on your phone

---

## 💡 Tips & Tricks

### For Best Responses:
- Be specific in your questions
- Questions work best for:
  - Information lookup (weather, news, research)
  - Code generation
  - Analysis and summarization
  - System status checks

### Response Time:
- Simple questions: 5-15 seconds
- Complex questions: 15-45 seconds
- Code generation: 20-60 seconds

### If No Response:
1. Check listener is running: `systemctl --user status milton-phone-listener`
2. Check API server: `curl localhost:8001/api/system-state`
3. View logs: `journalctl --user -u milton-phone-listener -n 50`
4. Restart listener: `systemctl --user restart milton-phone-listener`

---

## 🎯 Advanced: Custom Agent Selection

Want to route to specific agents?

### In Shortcut:
Add to message: `[CORTEX] Your question here`
- `[NEXUS]` - Research and general knowledge
- `[CORTEX]` - Code generation and technical tasks
- `[FRONTIER]` - Creative and experimental

### Via curl:
```bash
curl -d "[CORTEX] Write a bash script to backup my files" ntfy.sh/milton-briefing-code-ask
```

---

## 📋 Quick Reference

**Your Topics:**
- Questions: `${NTFY_TOPIC}-ask` (default: `milton-briefing-code-ask`)
- Responses: `${NTFY_TOPIC}` (default: `milton-briefing-code`)

**Service Commands:**
```bash
systemctl --user status milton-phone-listener      # Check status
systemctl --user restart milton-phone-listener     # Restart
journalctl --user -u milton-phone-listener -f      # View logs
```

---

## 🔗 Related Documentation

- [QUICK_START_IPHONE.md](QUICK_START_IPHONE.md) - Getting briefings
- [IPHONE_BRIEFING_SETUP.md](IPHONE_BRIEFING_SETUP.md) - Detailed setup
- [MORNING_BRIEFING_GUIDE.md](MORNING_BRIEFING_GUIDE.md) - Briefing system

---

**Now you can talk to your AI from anywhere! 🎉**
