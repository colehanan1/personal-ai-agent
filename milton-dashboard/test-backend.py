#!/usr/bin/env python3
"""
Simple test backend for Milton Dashboard
Provides mock endpoints so you can test the dashboard functionality
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sock import Sock
import time
import json
import random

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
sock = Sock(app)

# Mock system state
@app.route('/api/system-state', methods=['GET'])
def system_state():
    return jsonify({
        "nexus": {
            "status": "UP",
            "last_check": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        },
        "cortex": {
            "status": "UP",
            "running_jobs": 0,
            "queued_jobs": 1,
            "last_check": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        },
        "frontier": {
            "status": "UP",
            "last_check": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        },
        "memory": {
            "status": "UP",
            "vector_count": 1200,
            "memory_mb": 8.3,
            "last_check": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
    })

# Mock ask endpoint
@app.route('/api/ask', methods=['POST'])
def ask():
    data = request.json
    query = data.get('query', '')
    agent = data.get('agent')

    # Generate request ID
    request_id = f"req_{int(time.time())}_{random.randint(1000, 9999)}"

    # Determine agent
    if not agent:
        if 'paper' in query.lower() or 'research' in query.lower():
            agent_assigned = 'FRONTIER'
        elif 'code' in query.lower() or 'analyze' in query.lower():
            agent_assigned = 'CORTEX'
        else:
            agent_assigned = 'NEXUS'
    else:
        agent_assigned = agent

    return jsonify({
        "request_id": request_id,
        "status": "accepted",
        "agent_assigned": agent_assigned,
        "confidence": random.uniform(0.85, 0.98)
    })

# WebSocket endpoint for streaming
@sock.route('/ws/request/<request_id>')
def stream_request(ws, request_id):
    """Stream mock response messages"""

    # Send routing message
    ws.send(json.dumps({
        "type": "routing",
        "agent": "FRONTIER",
        "confidence": 0.94,
        "reasoning": "Query detected: research question",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }))
    time.sleep(0.5)

    # Send thinking messages
    thinking_messages = [
        "Analyzing query structure...",
        "Searching arXiv database...",
        "Filtering results by relevance...",
        "Extracting key findings..."
    ]

    for msg in thinking_messages:
        ws.send(json.dumps({
            "type": "thinking",
            "content": msg,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }))
        time.sleep(0.3)

    # Send token stream (response content)
    response_text = "Found 5 relevant papers from this week:\n\n1. Neural Architecture Search with Reinforcement Learning\n2. Attention Is All You Need: Transformers Revisited\n3. Deep Learning for Computer Vision: A Survey\n4. Generative AI in Healthcare Applications\n5. Quantum Machine Learning Advances"

    for word in response_text.split():
        ws.send(json.dumps({
            "type": "token",
            "content": word + " ",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }))
        time.sleep(0.05)

    # Send memory storage message
    ws.send(json.dumps({
        "type": "memory",
        "vector_id": f"vec_{random.randint(10000, 99999)}",
        "stored": True,
        "embedding_size": 1536,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }))
    time.sleep(0.3)

    # Send completion message
    ws.send(json.dumps({
        "type": "complete",
        "total_tokens": 287,
        "duration_ms": 3200,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }))

if __name__ == '__main__':
    print("=" * 70)
    print("Milton Dashboard Test Backend")
    print("=" * 70)
    print("Starting server at http://localhost:8001")
    print("Dashboard should connect automatically")
    print("=" * 70)
    print()

    app.run(host='localhost', port=8001, debug=True)
