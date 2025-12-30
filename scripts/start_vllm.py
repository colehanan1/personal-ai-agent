#!/usr/bin/env python3
"""
vLLM Server Startup Script
Starts the vLLM OpenAI-compatible API server with Llama 3.1 405B
"""
import subprocess
import sys
import os

def main():
    """Start vLLM server with optimized configuration for RTX 5090."""
    # Phase 2: Use Llama-3.1-8B-Instruct (located in milton/models/)
    model_path = os.path.expanduser("~/milton/models/Llama-3.1-8B-Instruct-HF")

    cmd = [
        sys.executable, "-m", "vllm.entrypoints.openai.api_server",
        "--model", model_path,
        "--served-model-name", "llama31-8b-instruct",
        "--chat-template", os.path.expanduser("~/milton/tools/llama31_instruct.jinja"),
        "--host", "127.0.0.1",
        "--port", "8000",
        "--dtype", "bfloat16",
        "--gpu-memory-utilization", "0.90",
        "--max-model-len", "8192",
        "--api-key", "dy537t7K6iEcE3Xr8O0N-6hStQ5veeGcRclhixvWvEo",
    ]

    print("=" * 70)
    print("Starting vLLM Server for Llama 3.1 8B (Phase 2)")
    print("=" * 70)
    print(f"Model path: {model_path}")
    print(f"Served model name: llama31-8b-instruct")
    print("Port: 8000")
    print("GPU Memory Utilization: 90%")
    print("\nThis will take 30-60 seconds on first run...")
    print("=" * 70)
    print()

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n\nShutting down vLLM server...")
        sys.exit(0)
    except Exception as e:
        print(f"\nError starting vLLM server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
