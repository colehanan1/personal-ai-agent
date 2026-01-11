"""
Strict JSON schema for benchmark results.

Defines comprehensive data structures for benchmark runs, metrics,
and system information with full error tracking.
"""
from __future__ import annotations

import platform
import socket
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any


class MetricStatus(str, Enum):
    """Status of an individual metric."""
    OK = "ok"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class SystemInfo:
    """System information for reproducibility."""
    hostname: str
    platform: str  # e.g., "Linux", "Darwin"
    platform_version: str
    python_version: str
    cpu_info: str
    cpu_count: int
    total_ram_gb: float
    gpu_info: Optional[str] = None
    cuda_version: Optional[str] = None
    
    @classmethod
    def collect(cls) -> SystemInfo:
        """Collect current system information."""
        import psutil
        
        # Get CPU info
        try:
            if platform.system() == "Linux":
                with open("/proc/cpuinfo") as f:
                    cpuinfo = f.read()
                    for line in cpuinfo.split("\n"):
                        if "model name" in line:
                            cpu_info = line.split(":")[1].strip()
                            break
                    else:
                        cpu_info = platform.processor() or "unknown"
            else:
                cpu_info = platform.processor() or "unknown"
        except Exception:
            cpu_info = "unknown"
        
        # Get GPU info
        gpu_info = None
        cuda_version = None
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                gpu_info = result.stdout.strip()
        except Exception:
            pass
        
        try:
            result = subprocess.run(
                ["nvcc", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "release" in line.lower():
                        cuda_version = line.strip()
                        break
        except Exception:
            pass
        
        return cls(
            hostname=socket.gethostname(),
            platform=platform.system(),
            platform_version=platform.release(),
            python_version=platform.python_version(),
            cpu_info=cpu_info,
            cpu_count=psutil.cpu_count(logical=True),
            total_ram_gb=round(psutil.virtual_memory().total / (1024**3), 2),
            gpu_info=gpu_info,
            cuda_version=cuda_version,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class MetricResult:
    """Result for a single metric measurement."""
    status: MetricStatus
    value: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "value": self.value,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass
class BenchmarkCandidate:
    """A model candidate for benchmarking."""
    version: str
    model_type: str  # e.g., "base", "distilled", "quantized"
    model_path: str
    base_model: str
    quantization: Optional[str] = None
    distilled_from: Optional[str] = None
    
    # Metrics
    latency_ms: MetricResult = field(default_factory=lambda: MetricResult(MetricStatus.SKIPPED))
    tokens_per_sec: MetricResult = field(default_factory=lambda: MetricResult(MetricStatus.SKIPPED))
    peak_vram_mb: MetricResult = field(default_factory=lambda: MetricResult(MetricStatus.SKIPPED))
    peak_ram_mb: MetricResult = field(default_factory=lambda: MetricResult(MetricStatus.SKIPPED))
    cove_pass_rate: MetricResult = field(default_factory=lambda: MetricResult(MetricStatus.SKIPPED))
    retrieval_score: MetricResult = field(default_factory=lambda: MetricResult(MetricStatus.SKIPPED))
    
    # Additional metadata
    file_size_mb: Optional[float] = None
    parameter_count: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version": self.version,
            "model_type": self.model_type,
            "model_path": self.model_path,
            "base_model": self.base_model,
            "quantization": self.quantization,
            "distilled_from": self.distilled_from,
            "file_size_mb": self.file_size_mb,
            "parameter_count": self.parameter_count,
            "metrics": {
                "latency_ms": self.latency_ms.to_dict(),
                "tokens_per_sec": self.tokens_per_sec.to_dict(),
                "peak_vram_mb": self.peak_vram_mb.to_dict(),
                "peak_ram_mb": self.peak_ram_mb.to_dict(),
                "cove_pass_rate": self.cove_pass_rate.to_dict(),
                "retrieval_score": self.retrieval_score.to_dict(),
            },
        }


@dataclass
class RunMetadata:
    """Metadata for a benchmark run."""
    run_id: str  # Format: benchmark_YYYYMMDD_HHMMSS
    timestamp: str  # ISO 8601 format
    git_sha: Optional[str] = None
    git_branch: Optional[str] = None
    git_dirty: bool = False
    command_line: Optional[str] = None
    dry_run: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def create(cls, dry_run: bool = False, command_line: Optional[str] = None) -> RunMetadata:
        """Create metadata for a new run."""
        now = datetime.now(timezone.utc)
        run_id = f"benchmark_{now.strftime('%Y%m%d_%H%M%S')}"
        
        # Get git info
        git_sha = None
        git_branch = None
        git_dirty = False
        
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                git_sha = result.stdout.strip()
        except Exception:
            pass
        
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                git_branch = result.stdout.strip()
        except Exception:
            pass
        
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                git_dirty = True
        except Exception:
            pass
        
        return cls(
            run_id=run_id,
            timestamp=now.isoformat(),
            git_sha=git_sha,
            git_branch=git_branch,
            git_dirty=git_dirty,
            command_line=command_line,
            dry_run=dry_run,
        )


@dataclass
class BenchmarkRun:
    """Complete benchmark run with all metadata and results."""
    metadata: RunMetadata
    system_info: SystemInfo
    candidates: List[BenchmarkCandidate]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "metadata": self.metadata.to_dict(),
            "system_info": self.system_info.to_dict(),
            "candidates": [c.to_dict() for c in self.candidates],
        }
    
    def save(self, output_path: Path) -> None:
        """Save benchmark run to JSON file."""
        import json
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, input_path: Path) -> BenchmarkRun:
        """Load benchmark run from JSON file."""
        import json
        
        with open(input_path, "r") as f:
            data = json.load(f)
        
        # Reconstruct objects
        metadata = RunMetadata(**data["metadata"])
        system_info = SystemInfo(**data["system_info"])
        
        candidates = []
        for c_data in data["candidates"]:
            # Extract metrics
            metrics_data = c_data.pop("metrics")
            
            # Create candidate
            candidate = BenchmarkCandidate(
                version=c_data["version"],
                model_type=c_data["model_type"],
                model_path=c_data["model_path"],
                base_model=c_data["base_model"],
                quantization=c_data.get("quantization"),
                distilled_from=c_data.get("distilled_from"),
                file_size_mb=c_data.get("file_size_mb"),
                parameter_count=c_data.get("parameter_count"),
            )
            
            # Reconstruct metrics
            for metric_name, metric_data in metrics_data.items():
                metric = MetricResult(
                    status=MetricStatus(metric_data["status"]),
                    value=metric_data.get("value"),
                    error_message=metric_data.get("error_message"),
                    metadata=metric_data.get("metadata", {}),
                )
                setattr(candidate, metric_name, metric)
            
            candidates.append(candidate)
        
        return cls(
            metadata=metadata,
            system_info=system_info,
            candidates=candidates,
        )
