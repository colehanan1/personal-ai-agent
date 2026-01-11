"""
Tests for edge bundle packager.
"""

import json
import shutil
import tarfile
import tempfile
from pathlib import Path

import pytest

from deployment.edge_packager import EdgePackager, BundleManifest


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Create model directory
        model_dir = tmpdir_path / "test_model"
        model_dir.mkdir()
        
        # Add some files
        (model_dir / "config.json").write_text('{"model_type": "llama"}')
        (model_dir / "tokenizer_config.json").write_text('{"vocab_size": 32000}')
        (model_dir / "model.safetensors").write_bytes(b"fake_model_data" * 100)
        
        # Create output directory
        output_dir = tmpdir_path / "bundles"
        output_dir.mkdir()
        
        yield {
            "tmpdir": tmpdir_path,
            "model_dir": model_dir,
            "output_dir": output_dir
        }


class TestBundleManifest:
    """Tests for BundleManifest."""
    
    def test_manifest_serialization(self):
        """Test manifest to/from JSON."""
        manifest = BundleManifest(
            bundle_id="bundle_test_123",
            created_at="2026-01-11T20:00:00",
            model_version="v1.0.0",
            model_path="/path/to/model",
            artifact_type="gguf",
            registry_entry={"version": "v1.0.0"},
            benchmark_summary={"score": 0.95},
            files={"config.json": "abc123"},
            total_size_bytes=1024
        )
        
        # Serialize
        json_str = manifest.to_json()
        data = json.loads(json_str)
        
        # Verify fields
        assert data["bundle_id"] == "bundle_test_123"
        assert data["model_version"] == "v1.0.0"
        assert data["artifact_type"] == "gguf"
        assert data["total_size_bytes"] == 1024
        
        # Deserialize
        manifest2 = BundleManifest.from_json(json_str)
        assert manifest2.bundle_id == manifest.bundle_id
        assert manifest2.artifact_type == manifest.artifact_type
        assert manifest2.files == manifest.files
    
    def test_manifest_to_dict(self):
        """Test manifest to dictionary."""
        manifest = BundleManifest(
            bundle_id="bundle_test",
            created_at="2026-01-11T20:00:00",
            model_version="v1.0.0",
            model_path="/path",
            artifact_type="hf-distilled",
            registry_entry={},
            benchmark_summary={},
            files={},
            total_size_bytes=0
        )
        
        data = manifest.to_dict()
        assert isinstance(data, dict)
        assert "bundle_id" in data
        assert "created_at" in data
        assert "artifact_type" in data
        assert data["artifact_type"] == "hf-distilled"


class TestEdgePackager:
    """Tests for EdgePackager."""
    
    def test_packager_init(self, temp_dirs):
        """Test packager initialization."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        assert packager.output_dir == temp_dirs["output_dir"]
        assert packager.output_dir.exists()
    
    def test_compute_file_hash(self, temp_dirs):
        """Test file hash computation."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        # Create test file
        test_file = temp_dirs["tmpdir"] / "test.txt"
        test_file.write_text("hello world")
        
        # Compute hash
        hash1 = packager._compute_file_hash(test_file)
        hash2 = packager._compute_file_hash(test_file)
        
        # Should be deterministic
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length
    
    def test_compute_dir_hashes(self, temp_dirs):
        """Test directory hash computation."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        # Compute hashes for model directory
        hashes = packager._compute_dir_hashes(temp_dirs["model_dir"])
        
        # Should have entries for all files
        assert "config.json" in hashes
        assert "tokenizer_config.json" in hashes
        assert "model.safetensors" in hashes
        
        # All should be valid SHA256 hashes
        for hash_val in hashes.values():
            assert len(hash_val) == 64
    
    def test_get_dir_size(self, temp_dirs):
        """Test directory size computation."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        size = packager._get_dir_size(temp_dirs["model_dir"])
        
        # Should be sum of all files
        expected = sum(
            f.stat().st_size
            for f in temp_dirs["model_dir"].rglob("*")
            if f.is_file()
        )
        assert size == expected
    
    def test_create_bundle(self, temp_dirs):
        """Test bundle creation."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        registry_entry = {
            "version": "v1.0.0",
            "path": str(temp_dirs["model_dir"]),
            "model_type": "llama"
        }
        
        benchmark_summary = {
            "score": 0.95,
            "metrics": {"latency": 15.5}
        }
        
        # Create bundle with HF directory
        bundle_path = packager.create_bundle(
            model_path=temp_dirs["model_dir"],
            registry_entry=registry_entry,
            benchmark_summary=benchmark_summary,
            artifact_type="hf-distilled"
        )
        
        # Verify bundle was created
        assert bundle_path.exists()
        assert bundle_path.suffix == ".gz"
        assert "milton_edge_bundle" in bundle_path.name
        
        # Verify it's a valid tarball
        assert tarfile.is_tarfile(bundle_path)
    
    def test_create_bundle_contents(self, temp_dirs):
        """Test bundle contains all expected files."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        bundle_path = packager.create_bundle(
            model_path=temp_dirs["model_dir"],
            registry_entry={"version": "v1.0.0"},
            benchmark_summary={"score": 0.95},
            artifact_type="hf-distilled"
        )
        
        # Extract and check contents
        with tarfile.open(bundle_path, "r:gz") as tar:
            members = [m.name for m in tar.getmembers()]
            
            # Check for required files
            assert any("manifest.json" in m for m in members)
            assert any("registry_entry.json" in m for m in members)
            assert any("benchmark_summary.json" in m for m in members)
            assert any("SHA256SUMS" in m for m in members)
            assert any("model/config.json" in m for m in members)
    
    def test_extract_manifest(self, temp_dirs):
        """Test manifest extraction from bundle."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        registry_entry = {"version": "v1.2.3"}
        benchmark_summary = {"score": 0.88}
        
        bundle_path = packager.create_bundle(
            model_path=temp_dirs["model_dir"],
            registry_entry=registry_entry,
            benchmark_summary=benchmark_summary,
            artifact_type="hf-distilled"
        )
        
        # Extract manifest
        manifest = packager.extract_manifest(bundle_path)
        
        # Verify manifest contents
        assert manifest.model_version == "v1.2.3"
        assert manifest.artifact_type == "hf-distilled"
        assert manifest.registry_entry == registry_entry
        assert manifest.benchmark_summary == benchmark_summary
        assert len(manifest.files) > 0
        assert manifest.total_size_bytes > 0
    
    def test_extract_manifest_missing_file(self, temp_dirs):
        """Test manifest extraction with missing bundle."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        missing_path = temp_dirs["output_dir"] / "missing.tar.gz"
        
        with pytest.raises(FileNotFoundError):
            packager.extract_manifest(missing_path)
    
    def test_list_bundles(self, temp_dirs):
        """Test listing bundles."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        # Create a few bundles
        for i in range(3):
            packager.create_bundle(
                model_path=temp_dirs["model_dir"],
                registry_entry={"version": f"v1.0.{i}"},
                benchmark_summary={"score": 0.9 + i * 0.01},
                artifact_type="hf-distilled"
            )
        
        # List bundles
        bundles = packager.list_bundles()
        
        assert len(bundles) == 3
        
        # Verify bundle info
        for bundle_info in bundles:
            assert "path" in bundle_info
            assert "bundle_id" in bundle_info
            assert "model_version" in bundle_info
            assert "created_at" in bundle_info
            assert "size_bytes" in bundle_info
    
    def test_bundle_name_format(self, temp_dirs):
        """Test bundle name follows expected format."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        bundle_path = packager.create_bundle(
            model_path=temp_dirs["model_dir"],
            registry_entry={"version": "v1.0.0"},
            benchmark_summary={},
            artifact_type="hf-distilled"
        )
        
        # Check name format: milton_edge_bundle_vX.X.X_YYYYMMDD_HHMMSS.tar.gz
        name = bundle_path.name
        assert name.startswith("milton_edge_bundle_")
        assert name.endswith(".tar.gz")
        assert "v1.0.0" in name
    
    def test_create_bundle_missing_model(self, temp_dirs):
        """Test bundle creation with missing model path."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        missing_path = temp_dirs["tmpdir"] / "nonexistent"
        
        with pytest.raises(FileNotFoundError):
            packager.create_bundle(
                model_path=missing_path,
                registry_entry={"version": "v1.0.0"},
                benchmark_summary={},
                artifact_type="hf-distilled"
            )
    
    def test_checksums_file_format(self, temp_dirs):
        """Test SHA256SUMS file has correct format."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        bundle_path = packager.create_bundle(
            model_path=temp_dirs["model_dir"],
            registry_entry={"version": "v1.0.0"},
            benchmark_summary={},
            artifact_type="hf-distilled"
        )
        
        # Extract and read SHA256SUMS
        with tarfile.open(bundle_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith("SHA256SUMS"):
                    checksums_file = tar.extractfile(member)
                    content = checksums_file.read().decode("utf-8")
                    
                    # Each line should be: <hash>  <filename>
                    lines = content.strip().split("\n")
                    assert len(lines) > 0
                    
                    for line in lines:
                        parts = line.split("  ", 1)
                        assert len(parts) == 2
                        hash_val, filename = parts
                        assert len(hash_val) == 64  # SHA256
                        assert len(filename) > 0


class TestGGUFBundling:
    """Tests for GGUF file bundling."""
    
    def test_create_gguf_bundle(self, temp_dirs):
        """Test creating bundle with single GGUF file."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        # Create a fake GGUF file
        gguf_file = temp_dirs["tmpdir"] / "model-q4_0.gguf"
        gguf_file.write_bytes(b"fake_gguf_data" * 1000)
        
        bundle_path = packager.create_bundle(
            model_path=gguf_file,
            registry_entry={"version": "v1.0.0"},
            benchmark_summary={"score": 0.95},
            artifact_type="gguf"
        )
        
        # Verify bundle created
        assert bundle_path.exists()
        assert tarfile.is_tarfile(bundle_path)
        
        # Extract and verify contents
        manifest = packager.extract_manifest(bundle_path)
        assert manifest.artifact_type == "gguf"
        assert "model-q4_0.gguf" in manifest.model_path
        assert len(manifest.files) == 1  # Only one GGUF file
        assert "model/model-q4_0.gguf" in manifest.files
    
    def test_gguf_bundle_size(self, temp_dirs):
        """Test GGUF bundle is much faster than directory."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        # Create GGUF file
        gguf_file = temp_dirs["tmpdir"] / "model.gguf"
        gguf_file.write_bytes(b"x" * 1000)
        
        import time
        start = time.time()
        bundle_path = packager.create_bundle(
            model_path=gguf_file,
            registry_entry={"version": "v1.0.0"},
            benchmark_summary={},
            artifact_type="gguf"
        )
        gguf_time = time.time() - start
        
        # Should be very fast (< 1 second)
        assert gguf_time < 1.0
        
        # Verify bundle is small
        bundle_size = bundle_path.stat().st_size
        assert bundle_size < 10_000  # < 10KB
    
    def test_gguf_wrong_type_fails(self, temp_dirs):
        """Test GGUF artifact_type with directory fails."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        with pytest.raises(ValueError, match="artifact_type='gguf' requires a file"):
            packager.create_bundle(
                model_path=temp_dirs["model_dir"],
                registry_entry={"version": "v1.0.0"},
                benchmark_summary={},
                artifact_type="gguf"
            )
    
    def test_hf_wrong_type_fails(self, temp_dirs):
        """Test hf-distilled artifact_type with file fails."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        gguf_file = temp_dirs["tmpdir"] / "model.gguf"
        gguf_file.write_bytes(b"data")
        
        with pytest.raises(ValueError, match="artifact_type='hf-distilled' requires a directory"):
            packager.create_bundle(
                model_path=gguf_file,
                registry_entry={"version": "v1.0.0"},
                benchmark_summary={},
                artifact_type="hf-distilled"
            )
    
    def test_invalid_artifact_type(self, temp_dirs):
        """Test invalid artifact_type fails."""
        packager = EdgePackager(output_dir=temp_dirs["output_dir"])
        
        with pytest.raises(ValueError, match="Invalid artifact_type"):
            packager.create_bundle(
                model_path=temp_dirs["model_dir"],
                registry_entry={"version": "v1.0.0"},
                benchmark_summary={},
                artifact_type="unknown"
            )
