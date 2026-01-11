"""
Tests for deployment manager.
"""

import json
import shutil
import tarfile
import tempfile
from pathlib import Path

import pytest

from deployment.deployment_manager import DeploymentManager, DeploymentRecord
from deployment.edge_packager import EdgePackager


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Create model directory
        model_dir = tmpdir_path / "test_model"
        model_dir.mkdir()
        (model_dir / "config.json").write_text('{"model_type": "llama"}')
        (model_dir / "tokenizer_config.json").write_text('{"vocab_size": 32000}')
        (model_dir / "model.safetensors").write_bytes(b"model_data")
        
        # Create bundle
        bundle_output = tmpdir_path / "bundles"
        bundle_output.mkdir()
        
        packager = EdgePackager(output_dir=bundle_output)
        bundle_path = packager.create_bundle(
            model_path=model_dir,
            registry_entry={"version": "v1.0.0"},
            benchmark_summary={"score": 0.95},
            artifact_type="hf-distilled"
        )
        
        # Create deployment directories
        deployment_dir = tmpdir_path / "deployments"
        history_dir = tmpdir_path / "history"
        
        yield {
            "tmpdir": tmpdir_path,
            "model_dir": model_dir,
            "bundle_path": bundle_path,
            "deployment_dir": deployment_dir,
            "history_dir": history_dir
        }


class TestDeploymentRecord:
    """Tests for DeploymentRecord."""
    
    def test_record_serialization(self):
        """Test record to/from JSON."""
        record = DeploymentRecord(
            deployment_id="deploy_v1.0.0_123",
            timestamp="2026-01-11T20:00:00",
            bundle_id="bundle_v1.0.0_123",
            model_version="v1.0.0",
            target_path="/path/to/deployment",
            status="success",
            checksum_verified=True,
            load_test_passed=True,
            error_message=None
        )
        
        # Serialize
        json_str = record.to_json()
        data = json.loads(json_str)
        
        # Verify fields
        assert data["deployment_id"] == "deploy_v1.0.0_123"
        assert data["status"] == "success"
        assert data["checksum_verified"] is True
        
        # Deserialize
        record2 = DeploymentRecord.from_dict(data)
        assert record2.deployment_id == record.deployment_id
        assert record2.checksum_verified == record.checksum_verified
    
    def test_record_with_error(self):
        """Test record with error message."""
        record = DeploymentRecord(
            deployment_id="deploy_v1.0.0_123",
            timestamp="2026-01-11T20:00:00",
            bundle_id="bundle_v1.0.0_123",
            model_version="v1.0.0",
            target_path="/path",
            status="failed",
            checksum_verified=False,
            load_test_passed=False,
            error_message="Checksum mismatch"
        )
        
        assert record.status == "failed"
        assert record.error_message == "Checksum mismatch"


class TestDeploymentManager:
    """Tests for DeploymentManager."""
    
    def test_manager_init(self, temp_dirs):
        """Test manager initialization."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        assert manager.deployment_dir == temp_dirs["deployment_dir"]
        assert manager.history_dir == temp_dirs["history_dir"]
        assert manager.deployment_dir.exists()
        assert manager.history_dir.exists()
    
    def test_verify_checksums_success(self, temp_dirs):
        """Test checksum verification with valid bundle."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        packager = EdgePackager()
        manifest = packager.extract_manifest(temp_dirs["bundle_path"])
        
        # Extract bundle
        with tempfile.TemporaryDirectory() as extract_dir:
            extract_path = Path(extract_dir)
            
            with tarfile.open(temp_dirs["bundle_path"], "r:gz") as tar:
                tar.extractall(extract_path)
            
            bundle_dirs = list(extract_path.glob("bundle_*"))
            assert len(bundle_dirs) == 1
            bundle_dir = bundle_dirs[0]
            
            # Verify checksums
            result = manager._verify_checksums(bundle_dir, manifest)
            assert result is True
    
    def test_verify_checksums_failure(self, temp_dirs):
        """Test checksum verification with corrupted file."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        packager = EdgePackager()
        manifest = packager.extract_manifest(temp_dirs["bundle_path"])
        
        # Extract and corrupt a file
        with tempfile.TemporaryDirectory() as extract_dir:
            extract_path = Path(extract_dir)
            
            with tarfile.open(temp_dirs["bundle_path"], "r:gz") as tar:
                tar.extractall(extract_path)
            
            bundle_dir = list(extract_path.glob("bundle_*"))[0]
            
            # Corrupt config.json
            config_file = bundle_dir / "model" / "config.json"
            config_file.write_text('{"corrupted": true}')
            
            # Verify checksums should fail
            result = manager._verify_checksums(bundle_dir, manifest)
            assert result is False
    
    def test_run_load_test_success(self, temp_dirs):
        """Test load test with valid model."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        success, error = manager._run_load_test(temp_dirs["model_dir"])
        assert success is True
        assert error is None
    
    def test_run_load_test_missing_config(self, temp_dirs):
        """Test load test with missing config.json."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        # Create model without config.json
        incomplete_model = temp_dirs["tmpdir"] / "incomplete_model"
        incomplete_model.mkdir()
        (incomplete_model / "tokenizer_config.json").write_text("{}")
        
        success, error = manager._run_load_test(incomplete_model)
        assert success is False
        assert "config.json" in error
    
    def test_run_load_test_invalid_json(self, temp_dirs):
        """Test load test with invalid config.json."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        # Create model with invalid JSON
        bad_model = temp_dirs["tmpdir"] / "bad_model"
        bad_model.mkdir()
        (bad_model / "config.json").write_text("not valid json")
        (bad_model / "tokenizer_config.json").write_text("{}")
        
        success, error = manager._run_load_test(bad_model)
        assert success is False
        assert "Invalid config.json" in error
    
    def test_deploy_bundle_dry_run(self, temp_dirs):
        """Test bundle deployment in dry-run mode."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        record = manager.deploy_bundle(
            bundle_path=temp_dirs["bundle_path"],
            dry_run=True
        )
        
        # Should succeed
        assert record.status == "success"
        assert record.checksum_verified is True
        assert record.load_test_passed is True
        
        # Should create history record
        record_path = manager.history_dir / f"{record.deployment_id}.json"
        assert record_path.exists()
    
    def test_deploy_bundle_actual(self, temp_dirs):
        """Test actual bundle deployment."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        target_path = temp_dirs["deployment_dir"] / "test_deployment"
        
        record = manager.deploy_bundle(
            bundle_path=temp_dirs["bundle_path"],
            target_path=target_path,
            dry_run=False
        )
        
        # Should succeed
        assert record.status == "success"
        
        # Should create deployment files
        assert target_path.exists()
        assert (target_path / "model").exists()
        assert (target_path / "manifest.json").exists()
        assert (target_path / "registry_entry.json").exists()
        assert (target_path / "benchmark_summary.json").exists()
        assert (target_path / "SHA256SUMS").exists()
        assert (target_path / "DEPLOYED_AT").exists()
    
    def test_deploy_bundle_skip_checksum(self, temp_dirs):
        """Test deployment with checksum verification skipped."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        record = manager.deploy_bundle(
            bundle_path=temp_dirs["bundle_path"],
            dry_run=True,
            verify_checksums=False
        )
        
        assert record.status == "success"
        assert record.checksum_verified is False
        assert record.load_test_passed is True
    
    def test_deploy_bundle_skip_load_test(self, temp_dirs):
        """Test deployment with load test skipped."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        record = manager.deploy_bundle(
            bundle_path=temp_dirs["bundle_path"],
            dry_run=True,
            run_load_test=False
        )
        
        assert record.status == "success"
        assert record.checksum_verified is True
        assert record.load_test_passed is False
    
    def test_deploy_bundle_missing_file(self, temp_dirs):
        """Test deployment with missing bundle file."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        missing_path = temp_dirs["tmpdir"] / "missing.tar.gz"
        
        with pytest.raises(FileNotFoundError):
            manager.deploy_bundle(bundle_path=missing_path)
    
    def test_list_deployments(self, temp_dirs):
        """Test listing deployment records."""
        import time
        
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        # Create a few deployments with slight delay to ensure unique timestamps
        for i in range(3):
            manager.deploy_bundle(
                bundle_path=temp_dirs["bundle_path"],
                dry_run=True
            )
            time.sleep(0.01)  # Small delay to ensure different timestamps
        
        # List deployments
        records = manager.list_deployments()
        
        assert len(records) >= 3  # At least 3 (may have duplicate second)
        
        # Should be sorted by timestamp (newest first)
        for i in range(len(records) - 1):
            assert records[i].timestamp >= records[i + 1].timestamp
    
    def test_get_last_successful_deployment(self, temp_dirs):
        """Test getting last successful deployment."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        # Create a successful deployment
        record1 = manager.deploy_bundle(
            bundle_path=temp_dirs["bundle_path"],
            dry_run=True
        )
        
        # Get last successful
        last = manager.get_last_successful_deployment()
        
        assert last is not None
        assert last.deployment_id == record1.deployment_id
        assert last.status == "success"
    
    def test_get_last_successful_none(self, temp_dirs):
        """Test getting last successful with no deployments."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        last = manager.get_last_successful_deployment()
        assert last is None
    
    def test_rollback_to_previous(self, temp_dirs):
        """Test rollback to previous deployment."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        # Create initial deployment
        record1 = manager.deploy_bundle(
            bundle_path=temp_dirs["bundle_path"],
            dry_run=True
        )
        
        # Rollback
        rollback_record = manager.rollback_to_previous(dry_run=True)
        
        assert rollback_record is not None
        assert rollback_record.deployment_id.startswith("rollback_")
        assert rollback_record.model_version == record1.model_version
        assert "Rolled back" in rollback_record.error_message
    
    def test_rollback_none_available(self, temp_dirs):
        """Test rollback with no previous deployment."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        rollback_record = manager.rollback_to_previous()
        assert rollback_record is None
    
    def test_deployment_overwrites_existing(self, temp_dirs):
        """Test that deployment overwrites existing target."""
        manager = DeploymentManager(
            deployment_dir=temp_dirs["deployment_dir"],
            history_dir=temp_dirs["history_dir"]
        )
        
        target_path = temp_dirs["deployment_dir"] / "test_target"
        
        # First deployment
        record1 = manager.deploy_bundle(
            bundle_path=temp_dirs["bundle_path"],
            target_path=target_path,
            dry_run=False
        )
        assert record1.status == "success"
        
        # Create a marker file
        marker = target_path / "marker.txt"
        marker.write_text("first deployment")
        
        # Second deployment to same path
        record2 = manager.deploy_bundle(
            bundle_path=temp_dirs["bundle_path"],
            target_path=target_path,
            dry_run=False
        )
        assert record2.status == "success"
        
        # Marker should be gone
        assert not marker.exists()
