#!/usr/bin/env python3
"""
Milton Chat Gateway - OpenAI-compatible API server for Open WebUI.

This script starts the Chat Gateway server that provides an OpenAI-compatible
API for use with Open WebUI and other compatible clients.

Usage:
    python scripts/start_chat_gateway.py

Environment Variables:
    MILTON_CHAT_HOST     - Host to bind to (default: 127.0.0.1)
    MILTON_CHAT_PORT     - Port to listen on (default: 8081)
    MILTON_CHAT_MODEL_ID - Model ID to expose (default: milton-local)
    LLM_API_URL          - Backend LLM API URL (default: http://localhost:8000)
    LLM_MODEL            - Backend LLM model name (default: llama31-8b-instruct)
    LLM_API_KEY          - Backend LLM API key (optional)
    MILTON_CHAT_MAX_TOKENS - Default max tokens (default: 4000)

Open WebUI Configuration:
    1. Go to Admin Panel > Settings > Connections
    2. Add OpenAI API connection:
       - API Base URL: http://HOST:PORT/v1
       - API Key: (any non-empty value, e.g., "sk-milton")
    3. Select "milton-local" model in chat

Example curl commands:
    # List models
    curl -s http://127.0.0.1:8081/v1/models | jq

    # Non-streaming chat
    curl -s http://127.0.0.1:8081/v1/chat/completions \\
      -H "Content-Type: application/json" \\
      -d '{"model":"milton-local","messages":[{"role":"user","content":"Hello!"}],"stream":false}' | jq

    # Streaming chat
    curl -N http://127.0.0.1:8081/v1/chat/completions \\
      -H "Content-Type: application/json" \\
      -d '{"model":"milton-local","messages":[{"role":"user","content":"Hello!"}],"stream":true}'
"""

import logging
import os
import socket
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_port_available(host: str, port: int) -> bool:
    """Check if a port is available for binding.
    
    Args:
        host: Host address to check
        port: Port number to check
        
    Returns:
        True if port is available, False if already in use
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.bind((host, port))
        sock.close()
        return True
    except OSError:
        return False
    finally:
        sock.close()


def main():
    """Start the Milton Chat Gateway server."""
    # Configure logging
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger("milton_gateway")

    # Import here to allow path setup
    try:
        import uvicorn
    except ImportError:
        logger.error(
            "uvicorn not installed. Install with: pip install uvicorn[standard]"
        )
        sys.exit(1)

    try:
        from milton_gateway.server import app, get_config
    except ImportError as e:
        logger.error(f"Failed to import milton_gateway: {e}")
        logger.error("Make sure you're running from the Milton repo root directory.")
        sys.exit(1)

    config = get_config()
    host = config["host"]
    port = config["port"]

    # Check if port is already in use
    if not check_port_available(host, port):
        logger.error("=" * 60)
        logger.error(f"ERROR: Port {port} is already in use")
        logger.error("=" * 60)
        logger.error("")
        logger.error("The gateway may already be running, or another service is using this port.")
        logger.error("")
        logger.error("To find what's using the port:")
        logger.error(f"  lsof -iTCP:{port} -sTCP:LISTEN -n -P")
        logger.error("")
        logger.error("To use a different port, set environment variable:")
        logger.error("  export MILTON_CHAT_PORT=8082")
        logger.error(f"  python {sys.argv[0]}")
        logger.error("")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Milton Chat Gateway")
    logger.info("=" * 60)
    logger.info(f"Server:     http://{host}:{port}")
    logger.info(f"Models:     http://{host}:{port}/v1/models")
    logger.info(f"Chat:       http://{host}:{port}/v1/chat/completions")
    logger.info(f"Health:     http://{host}:{port}/health")
    logger.info("-" * 60)
    logger.info(f"LLM Backend: {config['llm_api_url']}")
    logger.info(f"LLM Model:   {config['llm_model']}")
    logger.info(f"Exposed as:  {config['model_id']}")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Open WebUI Configuration:")
    logger.info(f"  API Base URL: http://{host}:{port}/v1")
    logger.info("  API Key: sk-milton (or any non-empty value)")
    logger.info(f"  Model: {config['model_id']}")
    logger.info("")

    # Start server
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()
