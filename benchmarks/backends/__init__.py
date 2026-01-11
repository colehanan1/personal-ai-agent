"""
Benchmark backends for measuring model inference performance.

Each backend implements a common interface for loading models and running
inference benchmarks with timing measurements.
"""
from benchmarks.backends.base import BenchmarkBackend
from benchmarks.backends.vllm_openai import VLLMOpenAIBackend

__all__ = [
    "BenchmarkBackend",
    "VLLMOpenAIBackend",
]
