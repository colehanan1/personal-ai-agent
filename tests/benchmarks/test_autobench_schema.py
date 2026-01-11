"""
Tests for autobench schema and runner.

Validates JSON schema, deterministic run IDs, and end-to-end benchmark workflow.
"""
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from benchmarks.schema import (
    BenchmarkRun,
    BenchmarkCandidate,
    MetricResult,
    MetricStatus,
    RunMetadata,
    SystemInfo,
)


class TestMetricResult:
    """Test MetricResult schema."""
    
    def test_ok_status(self):
        """Test metric with OK status."""
        metric = MetricResult(status=MetricStatus.OK, value=42.5)
        assert metric.status == MetricStatus.OK
        assert metric.value == 42.5
        assert metric.error_message is None
    
    def test_skipped_status(self):
        """Test metric with SKIPPED status."""
        metric = MetricResult(status=MetricStatus.SKIPPED)
        assert metric.status == MetricStatus.SKIPPED
        assert metric.value is None
        assert metric.error_message is None
    
    def test_error_status(self):
        """Test metric with ERROR status."""
        metric = MetricResult(
            status=MetricStatus.ERROR,
            error_message="Backend not available"
        )
        assert metric.status == MetricStatus.ERROR
        assert metric.value is None
        assert metric.error_message == "Backend not available"
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        metric = MetricResult(
            status=MetricStatus.OK,
            value=100.0,
            metadata={"unit": "ms"}
        )
        d = metric.to_dict()
        assert d["status"] == "ok"
        assert d["value"] == 100.0
        assert d["metadata"]["unit"] == "ms"


class TestBenchmarkCandidate:
    """Test BenchmarkCandidate schema."""
    
    def test_minimal_candidate(self):
        """Test candidate with minimal fields."""
        candidate = BenchmarkCandidate(
            version="v1.0",
            model_type="base",
            model_path="/path/to/model",
            base_model="llama-3.2-1b",
        )
        assert candidate.version == "v1.0"
        assert candidate.model_type == "base"
        assert candidate.quantization is None
        assert candidate.distilled_from is None
    
    def test_quantized_candidate(self):
        """Test quantized candidate."""
        candidate = BenchmarkCandidate(
            version="v1.0-4bit",
            model_type="quantized",
            model_path="/path/to/model",
            base_model="llama-3.2-1b",
            quantization="4bit",
        )
        assert candidate.quantization == "4bit"
    
    def test_default_metrics_skipped(self):
        """Test that metrics default to SKIPPED."""
        candidate = BenchmarkCandidate(
            version="v1.0",
            model_type="base",
            model_path="/path/to/model",
            base_model="llama-3.2-1b",
        )
        assert candidate.latency_ms.status == MetricStatus.SKIPPED
        assert candidate.tokens_per_sec.status == MetricStatus.SKIPPED
        assert candidate.peak_vram_mb.status == MetricStatus.SKIPPED
        assert candidate.peak_ram_mb.status == MetricStatus.SKIPPED
        assert candidate.cove_pass_rate.status == MetricStatus.SKIPPED
        assert candidate.retrieval_score.status == MetricStatus.SKIPPED
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        candidate = BenchmarkCandidate(
            version="v1.0",
            model_type="base",
            model_path="/path/to/model",
            base_model="llama-3.2-1b",
            file_size_mb=1024.5,
        )
        d = candidate.to_dict()
        assert d["version"] == "v1.0"
        assert d["model_type"] == "base"
        assert d["file_size_mb"] == 1024.5
        assert "metrics" in d
        assert "latency_ms" in d["metrics"]


class TestRunMetadata:
    """Test RunMetadata schema."""
    
    def test_create_metadata(self):
        """Test metadata creation."""
        metadata = RunMetadata.create(dry_run=True)
        assert metadata.run_id.startswith("benchmark_")
        assert metadata.dry_run is True
        assert metadata.timestamp is not None
    
    def test_run_id_format(self):
        """Test run ID format is deterministic."""
        metadata = RunMetadata.create()
        # Format: benchmark_YYYYMMDD_HHMMSS
        assert len(metadata.run_id) == len("benchmark_20260111_194318")
        assert metadata.run_id[0:10] == "benchmark_"
        
        # Verify timestamp format
        timestamp_part = metadata.run_id[10:]
        date_part, time_part = timestamp_part.split("_")
        assert len(date_part) == 8  # YYYYMMDD
        assert len(time_part) == 6  # HHMMSS
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        metadata = RunMetadata.create(command_line="python test.py")
        d = metadata.to_dict()
        assert d["run_id"].startswith("benchmark_")
        assert d["command_line"] == "python test.py"


class TestSystemInfo:
    """Test SystemInfo schema."""
    
    def test_collect_system_info(self):
        """Test system info collection."""
        info = SystemInfo.collect()
        assert info.hostname is not None
        assert info.platform is not None
        assert info.python_version is not None
        assert info.cpu_count > 0
        assert info.total_ram_gb > 0
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        info = SystemInfo.collect()
        d = info.to_dict()
        assert "hostname" in d
        assert "platform" in d
        assert "cpu_count" in d


class TestBenchmarkRun:
    """Test BenchmarkRun schema and serialization."""
    
    def test_create_minimal_run(self):
        """Test creating minimal benchmark run."""
        metadata = RunMetadata.create()
        system_info = SystemInfo.collect()
        candidates = []
        
        run = BenchmarkRun(
            metadata=metadata,
            system_info=system_info,
            candidates=candidates,
        )
        
        assert run.metadata.run_id is not None
        assert run.system_info.hostname is not None
        assert len(run.candidates) == 0
    
    def test_create_run_with_candidates(self):
        """Test run with multiple candidates."""
        metadata = RunMetadata.create()
        system_info = SystemInfo.collect()
        
        candidates = [
            BenchmarkCandidate(
                version="v1.0",
                model_type="base",
                model_path="/path/to/model1",
                base_model="llama-3.2-1b",
            ),
            BenchmarkCandidate(
                version="v1.0-4bit",
                model_type="quantized",
                model_path="/path/to/model2",
                base_model="llama-3.2-1b",
                quantization="4bit",
            ),
        ]
        
        run = BenchmarkRun(
            metadata=metadata,
            system_info=system_info,
            candidates=candidates,
        )
        
        assert len(run.candidates) == 2
        assert run.candidates[0].version == "v1.0"
        assert run.candidates[1].quantization == "4bit"
    
    def test_save_and_load(self):
        """Test saving and loading benchmark run."""
        metadata = RunMetadata.create(dry_run=True)
        system_info = SystemInfo.collect()
        
        candidate = BenchmarkCandidate(
            version="v1.0",
            model_type="base",
            model_path="/path/to/model",
            base_model="llama-3.2-1b",
            file_size_mb=500.0,
        )
        candidate.latency_ms = MetricResult(status=MetricStatus.OK, value=125.5)
        
        run = BenchmarkRun(
            metadata=metadata,
            system_info=system_info,
            candidates=[candidate],
        )
        
        # Save to temp file
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_run.json"
            run.save(output_path)
            
            # Verify file exists
            assert output_path.exists()
            
            # Load and verify
            loaded_run = BenchmarkRun.load(output_path)
            assert loaded_run.metadata.run_id == metadata.run_id
            assert loaded_run.metadata.dry_run is True
            assert len(loaded_run.candidates) == 1
            assert loaded_run.candidates[0].version == "v1.0"
            assert loaded_run.candidates[0].latency_ms.status == MetricStatus.OK
            assert loaded_run.candidates[0].latency_ms.value == 125.5
    
    def test_json_schema_valid(self):
        """Test that generated JSON is valid."""
        metadata = RunMetadata.create()
        system_info = SystemInfo.collect()
        
        candidate = BenchmarkCandidate(
            version="v1.0",
            model_type="base",
            model_path="/path/to/model",
            base_model="llama-3.2-1b",
        )
        
        run = BenchmarkRun(
            metadata=metadata,
            system_info=system_info,
            candidates=[candidate],
        )
        
        # Convert to dict and JSON
        d = run.to_dict()
        json_str = json.dumps(d, indent=2)
        
        # Verify can parse back
        parsed = json.loads(json_str)
        assert "metadata" in parsed
        assert "system_info" in parsed
        assert "candidates" in parsed
        assert parsed["metadata"]["run_id"].startswith("benchmark_")
    
    def test_json_with_errors(self):
        """Test JSON serialization with error metrics."""
        metadata = RunMetadata.create()
        system_info = SystemInfo.collect()
        
        candidate = BenchmarkCandidate(
            version="v1.0",
            model_type="base",
            model_path="/nonexistent/path",
            base_model="llama-3.2-1b",
        )
        candidate.latency_ms = MetricResult(
            status=MetricStatus.ERROR,
            error_message="Model file not found"
        )
        
        run = BenchmarkRun(
            metadata=metadata,
            system_info=system_info,
            candidates=[candidate],
        )
        
        # Save and load
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_run.json"
            run.save(output_path)
            
            loaded_run = BenchmarkRun.load(output_path)
            assert loaded_run.candidates[0].latency_ms.status == MetricStatus.ERROR
            assert "not found" in loaded_run.candidates[0].latency_ms.error_message


class TestDeterministicRunId:
    """Test deterministic run ID format."""
    
    def test_run_id_uniqueness(self):
        """Test that run IDs are unique across calls."""
        import time
        
        metadata1 = RunMetadata.create()
        time.sleep(1.1)  # Sleep to ensure different second
        metadata2 = RunMetadata.create()
        
        # Different runs should have different IDs
        assert metadata1.run_id != metadata2.run_id
    
    def test_run_id_sortable(self):
        """Test that run IDs are lexicographically sortable by time."""
        import time
        
        ids = []
        for _ in range(3):
            metadata = RunMetadata.create()
            ids.append(metadata.run_id)
            time.sleep(1.1)
        
        # IDs should be in ascending order
        assert ids == sorted(ids)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
