"""
Base interface for benchmark backends.

Defines the common interface that all backends must implement for
consistent benchmarking across different inference engines.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class InferenceResult:
    """Result from a single inference call."""
    prompt: str
    response: str
    first_token_latency_ms: Optional[float] = None
    total_latency_ms: Optional[float] = None
    tokens_generated: Optional[int] = None
    tokens_per_sec: Optional[float] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BenchmarkBackend(ABC):
    """
    Abstract base class for benchmark backends.
    
    Each backend must implement methods for:
    - Checking availability
    - Running inference with timing
    - Cleanup
    """
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the backend is available for benchmarking.
        
        Returns:
            True if backend is ready, False otherwise
        """
        pass
    
    @abstractmethod
    def get_availability_error(self) -> Optional[str]:
        """
        Get detailed error message if backend is not available.
        
        Returns:
            Error message or None if available
        """
        pass
    
    @abstractmethod
    def run_inference(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        **kwargs,
    ) -> InferenceResult:
        """
        Run a single inference with timing measurements.
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional backend-specific parameters
        
        Returns:
            InferenceResult with timing data
        """
        pass
    
    @abstractmethod
    def warmup(self, num_iterations: int = 3) -> None:
        """
        Warm up the backend with test inferences.
        
        Args:
            num_iterations: Number of warmup iterations
        """
        pass
    
    def cleanup(self) -> None:
        """
        Clean up resources.
        
        Optional method for backends that need cleanup.
        """
        pass
    
    def get_backend_info(self) -> Dict[str, Any]:
        """
        Get information about the backend.
        
        Returns:
            Dictionary with backend metadata
        """
        return {
            "backend_type": self.__class__.__name__,
        }
