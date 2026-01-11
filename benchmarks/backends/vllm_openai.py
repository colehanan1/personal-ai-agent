"""
vLLM OpenAI-compatible backend for benchmarking.

Connects to a running vLLM server via OpenAI-compatible API and measures
inference latency and throughput with streaming support.
"""
from __future__ import annotations

import os
import time
from typing import Optional, Dict, Any

import requests

from benchmarks.backends.base import BenchmarkBackend, InferenceResult


class VLLMOpenAIBackend(BenchmarkBackend):
    """
    Backend for vLLM OpenAI-compatible API server.
    
    Expects server running at http://localhost:8000 with standard
    OpenAI-compatible endpoints (/v1/chat/completions).
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        model_name: str = "llama31-8b-instruct",
        timeout: int = 120,
    ):
        """
        Initialize vLLM backend.
        
        Args:
            base_url: Base URL of vLLM server
            api_key: Optional API key for authentication
            model_name: Model name to use in requests
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("VLLM_API_KEY") or os.getenv("LLM_API_KEY")
        self.model_name = model_name
        self.timeout = timeout
        self._last_error = None
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    def is_available(self) -> bool:
        """Check if vLLM server is running and responsive."""
        try:
            response = requests.get(
                f"{self.base_url}/v1/models",
                headers=self._get_headers(),
                timeout=5,
            )
            if response.status_code == 200:
                self._last_error = None
                return True
            else:
                self._last_error = f"Server returned status {response.status_code}"
                return False
        except requests.exceptions.ConnectionError:
            self._last_error = f"Cannot connect to server at {self.base_url}"
            return False
        except Exception as e:
            self._last_error = f"Health check failed: {str(e)}"
            return False
    
    def get_availability_error(self) -> Optional[str]:
        """Get detailed error message if not available."""
        if not self.is_available():
            return self._last_error
        return None
    
    def run_inference(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        **kwargs,
    ) -> InferenceResult:
        """
        Run inference with timing measurements.
        
        Measures:
        - First token latency (via streaming)
        - Total latency
        - Tokens per second
        """
        if not self.is_available():
            return InferenceResult(
                prompt=prompt,
                response="",
                error=self._last_error,
            )
        
        # Prepare request
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            **kwargs,
        }
        
        try:
            start_time = time.perf_counter()
            first_token_time = None
            response_text = ""
            tokens_generated = 0
            
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._get_headers(),
                json=payload,
                stream=True,
                timeout=self.timeout,
            )
            response.raise_for_status()
            
            # Process streaming response
            for line in response.iter_lines():
                if not line:
                    continue
                
                line = line.decode('utf-8')
                if not line.startswith('data: '):
                    continue
                
                data_str = line[6:]  # Remove 'data: ' prefix
                if data_str == '[DONE]':
                    break
                
                try:
                    import json
                    data = json.loads(data_str)
                    
                    # Get first token timing
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    
                    # Extract content
                    choices = data.get('choices', [])
                    if choices:
                        delta = choices[0].get('delta', {})
                        content = delta.get('content', '')
                        if content:
                            response_text += content
                            # Rough token count (not exact, but close)
                            tokens_generated += len(content.split())
                
                except json.JSONDecodeError:
                    continue
            
            end_time = time.perf_counter()
            
            # Calculate metrics
            total_latency_ms = (end_time - start_time) * 1000
            first_token_latency_ms = None
            if first_token_time:
                first_token_latency_ms = (first_token_time - start_time) * 1000
            
            tokens_per_sec = None
            if tokens_generated > 0 and total_latency_ms > 0:
                tokens_per_sec = (tokens_generated / total_latency_ms) * 1000
            
            return InferenceResult(
                prompt=prompt,
                response=response_text,
                first_token_latency_ms=first_token_latency_ms,
                total_latency_ms=total_latency_ms,
                tokens_generated=tokens_generated,
                tokens_per_sec=tokens_per_sec,
                metadata={
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
        
        except requests.exceptions.Timeout:
            return InferenceResult(
                prompt=prompt,
                response="",
                error=f"Request timeout after {self.timeout}s",
            )
        except requests.exceptions.RequestException as e:
            return InferenceResult(
                prompt=prompt,
                response="",
                error=f"Request failed: {str(e)}",
            )
        except Exception as e:
            return InferenceResult(
                prompt=prompt,
                response="",
                error=f"Unexpected error: {str(e)}",
            )
    
    def warmup(self, num_iterations: int = 3) -> None:
        """Warm up the model with test inferences."""
        warmup_prompt = "Hello, this is a warmup test."
        for _ in range(num_iterations):
            self.run_inference(warmup_prompt, max_tokens=10, temperature=0.0)
    
    def get_backend_info(self) -> Dict[str, Any]:
        """Get backend information."""
        info = super().get_backend_info()
        info.update({
            "backend_type": "vllm_openai",
            "base_url": self.base_url,
            "model_name": self.model_name,
            "timeout": self.timeout,
        })
        
        # Try to get model info from server
        if self.is_available():
            try:
                response = requests.get(
                    f"{self.base_url}/v1/models",
                    headers=self._get_headers(),
                    timeout=5,
                )
                if response.status_code == 200:
                    data = response.json()
                    models = data.get('data', [])
                    if models:
                        info["available_models"] = [m.get('id') for m in models]
            except Exception:
                pass
        
        return info
