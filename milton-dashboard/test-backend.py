#!/usr/bin/env python3
"""
Simple test backend for Milton Dashboard
Provides mock endpoints with SMART responses based on query type
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
            "queued_jobs": 0,
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

def classify_query(query):
    """Determine query type and appropriate agent"""
    q = query.lower()

    # Simple conversational queries -> NEXUS (direct response)
    if any(word in q for word in ['hi', 'hello', 'hey', 'what do', 'who are', 'how are', 'whats up']):
        return 'NEXUS', 'conversational'

    # Research queries -> FRONTIER (complex response)
    if any(word in q for word in ['paper', 'research', 'arxiv', 'study', 'publication']):
        return 'FRONTIER', 'research'

    # Code/analysis queries -> CORTEX (medium response)
    if any(word in q for word in ['code', 'analyze', 'run', 'execute', 'function', 'algorithm']):
        return 'CORTEX', 'code'

    # Default to NEXUS for simple queries
    return 'NEXUS', 'simple'

# Mock ask endpoint
@app.route('/api/ask', methods=['POST'])
def ask():
    data = request.json
    query = data.get('query', '')
    agent_override = data.get('agent')

    # Generate request ID
    request_id = f"req_{int(time.time())}_{random.randint(1000, 9999)}"

    # Determine agent and query type
    if agent_override:
        agent_assigned = agent_override
        query_type = 'simple'  # User forced, keep simple
    else:
        agent_assigned, query_type = classify_query(query)

    return jsonify({
        "request_id": request_id,
        "status": "accepted",
        "agent_assigned": agent_assigned,
        "confidence": random.uniform(0.85, 0.98),
        "query_type": query_type  # Pass to WebSocket
    })

# WebSocket endpoint for streaming
@sock.route('/ws/request/<request_id>')
def stream_request(ws, request_id):
    """Stream response messages based on query complexity"""

    # Get query type from first message (in real system this would be in session)
    # For mock, we'll just detect from timing/context
    # Let's make it simple for conversational, complex for research

    # Receive initial context if sent
    query_type = 'simple'  # Default

    # Send routing message
    ws.send(json.dumps({
        "type": "routing",
        "agent": "NEXUS",
        "confidence": 0.92,
        "reasoning": "Simple conversational query",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }))
    time.sleep(0.3)

    # For SIMPLE queries, minimal thinking
    if query_type in ['conversational', 'simple']:
        ws.send(json.dumps({
            "type": "thinking",
            "content": "Processing query...",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }))
        time.sleep(0.2)

        # Short response
        response = "I'm Milton, your AI assistant. I don't have personal information about you stored yet, but I'm here to help with research, code, and general questions!"

        words = response.split()
        for i in range(0, len(words), 3):  # Send 3 words at a time for speed
            chunk = ' '.join(words[i:i+3]) + ' '
            ws.send(json.dumps({
                "type": "token",
                "content": chunk,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }))
            time.sleep(0.05)

        # Memory (optional for simple queries)
        ws.send(json.dumps({
            "type": "memory",
            "vector_id": f"vec_{random.randint(10000, 99999)}",
            "stored": True,
            "embedding_size": 1536,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }))
        time.sleep(0.1)

        # Completion
        ws.send(json.dumps({
            "type": "complete",
            "total_tokens": len(response.split()),
            "duration_ms": 800,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }))

    else:
        # COMPLEX query (research, code, etc.)
        thinking_messages = [
            "Analyzing query structure...",
            "Searching knowledge base...",
            "Filtering results...",
            "Preparing response..."
        ]

        for msg in thinking_messages:
            ws.send(json.dumps({
                "type": "thinking",
                "content": msg,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }))
            time.sleep(0.3)

        # Longer response for research
        response = "Found 5 relevant papers:\n\n1. Neural Architecture Search\n2. Transformer Models Survey\n3. Deep Learning Applications\n4. Generative AI Methods\n5. Quantum ML Advances"

        for word in response.split():
            ws.send(json.dumps({
                "type": "token",
                "content": word + " ",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }))
            time.sleep(0.05)

        ws.send(json.dumps({
            "type": "memory",
            "vector_id": f"vec_{random.randint(10000, 99999)}",
            "stored": True,
            "embedding_size": 1536,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }))
        time.sleep(0.2)

        ws.send(json.dumps({
            "type": "complete",
            "total_tokens": 287,
            "duration_ms": 3200,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }))

if __name__ == '__main__':
    print("=" * 70)
    print("Milton Dashboard Test Backend (SMART MODE)")
    print("=" * 70)
    print("Starting server at http://localhost:8001")
    print("Query routing:")
    print("  - Simple questions → Fast, short responses")
    print("  - Research queries → Detailed, multi-step responses")
    print("  - Code queries → Medium complexity responses")
    print("=" * 70)
    print()

    app.run(host='localhost', port=8001, debug=True, use_reloader=False)
