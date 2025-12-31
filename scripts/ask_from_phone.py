#!/home/cole-hanan/miniconda3/envs/milton/bin/python3
"""
Ask Milton Questions from Your iPhone
Listens to ntfy topic for incoming questions and sends back AI responses
"""
import os
import sys
import time
import json
import requests
import websocket
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

load_dotenv()

# Configuration
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "milton-briefing-code")
QUESTIONS_TOPIC = f"{NTFY_TOPIC}-ask"  # Separate topic for questions
API_URL = "http://localhost:8001"


def send_response_to_phone(response_text, topic=None):
    """Send AI response back to iPhone via ntfy."""
    if not topic:
        topic = NTFY_TOPIC

    try:
        result = requests.post(
            f"https://ntfy.sh/{topic}",
            data=response_text.encode('utf-8'),
            headers={
                "Title": "Milton AI Response",
                "Priority": "high",
                "Tags": "robot,speech_balloon"
            },
            timeout=10
        )
        return result.status_code == 200
    except Exception as e:
        print(f"Error sending response: {e}")
        return False


def ask_milton(question, agent=None):
    """Send question to Milton API and get response."""
    try:
        # Submit question
        payload = {"query": question}
        if agent:
            payload["agent"] = agent

        resp = requests.post(f"{API_URL}/api/ask", json=payload, timeout=5)
        resp.raise_for_status()
        request_id = resp.json()["request_id"]

        print(f"📝 Question submitted: {question[:60]}...", flush=True)
        print(f"   Request ID: {request_id}", flush=True)

        # Connect to WebSocket to get response
        ws_url = f"ws://localhost:8001/ws/request/{request_id}"
        ws = websocket.create_connection(ws_url, timeout=60)

        full_response = ""
        start = time.time()

        try:
            while time.time() - start < 60:
                msg_str = ws.recv()
                msg = json.loads(msg_str)

                if msg["type"] == "token":
                    full_response += msg.get("content", "")
                elif msg["type"] == "complete":
                    ws.close()
                    print(f"✅ Got response ({len(full_response)} chars)", flush=True)
                    return full_response if full_response else "No response received"
                elif msg["type"] == "error":
                    ws.close()
                    return f"❌ Error: {msg.get('error', 'Unknown error')}"

            ws.close()
            return full_response if full_response else "⏱️ Request timed out"

        except Exception as e:
            ws.close()
            if full_response:
                return full_response
            return f"❌ WebSocket error: {str(e)}"

    except Exception as e:
        return f"❌ Error submitting question: {str(e)}"


def listen_for_questions():
    """Listen to ntfy topic for incoming questions."""
    print("=" * 70, flush=True)
    print("MILTON PHONE LISTENER", flush=True)
    print("=" * 70, flush=True)
    print(f"Listening topic: {QUESTIONS_TOPIC}", flush=True)
    print(f"Response topic:  {NTFY_TOPIC}", flush=True)
    print(flush=True)
    print("Send questions from your iPhone using:", flush=True)
    print(f"  curl -d 'Your question here' ntfy.sh/{QUESTIONS_TOPIC}", flush=True)
    print(flush=True)
    print("Or use the ntfy app's 'Send' feature!", flush=True)
    print("=" * 70, flush=True)
    print(flush=True)

    # Subscribe to ntfy stream
    url = f"https://ntfy.sh/{QUESTIONS_TOPIC}/json"

    try:
        with requests.get(url, stream=True, timeout=None) as response:
            print(f"✅ Connected to {QUESTIONS_TOPIC}", flush=True)
            print("Waiting for questions...\n", flush=True)

            for line in response.iter_lines():
                if line:
                    try:
                        data = json.loads(line)

                        # Check if it's a message (not just keepalive)
                        if data.get("event") == "message":
                            message = data.get("message", "").strip()

                            if message and not message.startswith("This is a test"):
                                timestamp = datetime.now().strftime('%H:%M:%S')
                                print(f"[{timestamp}] 📱 Question received: {message[:60]}...", flush=True)

                                # Get AI response
                                print(f"[{timestamp}] 🤖 Processing...", flush=True)
                                ai_response = ask_milton(message)

                                # Send response back to phone
                                formatted_response = f"Q: {message}\n\n{ai_response}"
                                if send_response_to_phone(formatted_response):
                                    print(f"[{timestamp}] ✅ Response sent to iPhone\n", flush=True)
                                else:
                                    print(f"[{timestamp}] ❌ Failed to send response\n", flush=True)

                    except json.JSONDecodeError:
                        continue

    except KeyboardInterrupt:
        print("\n\n👋 Stopped listening")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ask Milton from your iPhone")
    parser.add_argument("--listen", action="store_true", help="Start listening for questions")
    parser.add_argument("--ask", help="Ask a question directly")
    parser.add_argument("--agent", help="Specify agent (NEXUS, CORTEX, FRONTIER)")
    args = parser.parse_args()

    if args.listen:
        listen_for_questions()
    elif args.ask:
        print(f"Question: {args.ask}")
        response = ask_milton(args.ask, args.agent)
        print(f"\nResponse:\n{response}")

        # Optionally send to phone
        send_to_phone = input("\nSend to iPhone? (y/n): ").lower().strip()
        if send_to_phone == 'y':
            if send_response_to_phone(f"Q: {args.ask}\n\n{response}"):
                print("✅ Sent to iPhone")
            else:
                print("❌ Failed to send")
    else:
        parser.print_help()
        print("\nQuick examples:")
        print(f"  # Listen for questions from iPhone:")
        print(f"  {sys.argv[0]} --listen")
        print()
        print(f"  # Ask a question from terminal:")
        print(f"  {sys.argv[0]} --ask 'What is the weather?'")
