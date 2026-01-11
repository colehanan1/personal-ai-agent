"""
Integration tests for autobench runner.

Tests end-to-end workflow including registry enumeration and JSON output.
"""
import json
import tempfile
from pathlib import Path

import pytest

from training.model_registry import ModelRegistry
from scripts.run_autobench import (
    run_benchmark,
    enumerate_candidates,
    create_candidate_from_registry_entry,
)
from benchmarks.schema import MetricStatus


class TestAutobenchRunner:
    """Test autobench runner integration."""
    
    def test_enumerate_empty_registry(self):
        """Test enumeration with empty registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.json"
            registry = ModelRegistry(registry_path=registry_path)
            
            candidates = enumerate_candidates(registry)
            assert len(candidates) == 0
    
    def test_enumerate_registry_with_models(self):
        """Test enumeration with populated registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.json"
            models_dir = Path(tmpdir) / "models"
            models_dir.mkdir()
            
            registry = ModelRegistry(
                registry_path=registry_path,
                models_dir=models_dir
            )
            
            # Create a fake model file
            model_path = models_dir / "test_model.gguf"
            model_path.write_text("fake model data" * 10000)
            
            # Register model
            registry.register_model(
                version="v1.0",
                base_model="llama-3.2-1b",
                model_path=model_path,
                metrics={"test": 1.0},
                quantization="4bit",
            )
            
            # Enumerate
            candidates = enumerate_candidates(registry)
            assert len(candidates) == 1
            assert candidates[0].version == "v1.0"
            assert candidates[0].quantization == "4bit"
            assert candidates[0].file_size_mb is not None
            assert candidates[0].file_size_mb >= 0
    
    def test_candidate_from_missing_model(self):
        """Test candidate creation when model file is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.json"
            models_dir = Path(tmpdir) / "models"
            
            registry = ModelRegistry(
                registry_path=registry_path,
                models_dir=models_dir
            )
            
            # Register model that doesn't exist
            registry.register_model(
                version="v1.0",
                base_model="llama-3.2-1b",
                model_path=Path("/nonexistent/path"),
                metrics={},
            )
            
            entry = registry.get_model("v1.0")
            candidate = create_candidate_from_registry_entry(entry)
            
            # All metrics should be ERROR status
            assert candidate.latency_ms.status == MetricStatus.ERROR
            assert "does not exist" in candidate.latency_ms.error_message
            assert candidate.file_size_mb is None
    
    def test_run_benchmark_dry_run(self):
        """Test full benchmark run in dry-run mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.json"
            models_dir = Path(tmpdir) / "models"
            output_dir = Path(tmpdir) / "benchmarks"
            models_dir.mkdir()
            
            # Create registry with test model
            registry = ModelRegistry(
                registry_path=registry_path,
                models_dir=models_dir
            )
            
            model_path = models_dir / "test_model.gguf"
            model_path.write_text("fake model data" * 1000)
            
            registry.register_model(
                version="v1.0-test",
                base_model="test-base",
                model_path=model_path,
                metrics={"perplexity": 5.0},
                quantization="8bit",
                distilled_from="test_adapter",
            )
            
            # Run benchmark
            output_path = run_benchmark(
                registry_path=registry_path,
                output_dir=output_dir,
                dry_run=True,
            )
            
            # Verify output file exists
            assert output_path.exists()
            assert output_path.name.startswith("benchmark_")
            assert output_path.suffix == ".json"
            
            # Validate JSON content
            with open(output_path) as f:
                data = json.load(f)
            
            assert data["metadata"]["dry_run"] is True
            assert data["metadata"]["run_id"].startswith("benchmark_")
            assert data["system_info"]["hostname"] is not None
            assert len(data["candidates"]) == 1
            
            candidate = data["candidates"][0]
            assert candidate["version"] == "v1.0-test"
            assert candidate["model_type"] == "quantized+distilled"
            assert candidate["quantization"] == "8bit"
            assert candidate["distilled_from"] == "test_adapter"
            assert candidate["file_size_mb"] > 0
            
            # All metrics should be skipped (no backend)
            for metric in ["latency_ms", "tokens_per_sec", "peak_vram_mb",
                          "peak_ram_mb", "cove_pass_rate", "retrieval_score"]:
                assert candidate["metrics"][metric]["status"] == "skipped"
    
    def test_multiple_model_types(self):
        """Test enumeration with multiple model types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.json"
            models_dir = Path(tmpdir) / "models"
            output_dir = Path(tmpdir) / "benchmarks"
            models_dir.mkdir()
            
            registry = ModelRegistry(
                registry_path=registry_path,
                models_dir=models_dir
            )
            
            # Create different model types
            for i, (quant, distilled) in enumerate([
                (None, None),  # base
                ("4bit", None),  # quantized
                (None, "adapter1"),  # distilled
                ("8bit", "adapter2"),  # quantized+distilled
            ]):
                model_path = models_dir / f"model_{i}.gguf"
                model_path.write_text(f"model {i}")
                
                registry.register_model(
                    version=f"v{i}",
                    base_model="test-base",
                    model_path=model_path,
                    metrics={},
                    quantization=quant,
                    distilled_from=distilled,
                )
            
            # Run benchmark
            output_path = run_benchmark(
                registry_path=registry_path,
                output_dir=output_dir,
                dry_run=True,
            )
            
            # Load and verify
            with open(output_path) as f:
                data = json.load(f)
            
            assert len(data["candidates"]) == 4
            
            # Verify model types
            types = [c["model_type"] for c in data["candidates"]]
            assert "base" in types
            assert "quantized" in types
            assert "distilled" in types
            assert "quantized+distilled" in types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
