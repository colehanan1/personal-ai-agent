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
    model_path = os.path.expanduser("~/agent-system/models/llama-405b")

    cmd = [
        sys.executable, "-m", "vllm.entrypoints.openai.api_server",
        "--model", model_path,
        "--quantization", "awq",
        "--tensor-parallel-size", "1",
        "--gpu-memory-utilization", "0.95",
        "--port", "8000",
        "--max-model-len", "4096",
        "--host", "0.0.0.0",
    ]

    print("=" * 70)
    print("Starting vLLM Server for Llama 3.1 405B")
    print("=" * 70)
    print(f"Model path: {model_path}")
    print("Port: 8000")
    print("Quantization: AWQ")
    print("GPU Memory Utilization: 95%")
    print("\nThis will take 2-3 minutes on first run...")
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
