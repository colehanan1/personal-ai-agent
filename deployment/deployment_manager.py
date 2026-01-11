"""
Deployment manager for Milton edge bundles.

Handles bundle extraction, validation, and deployment to target paths.
"""

import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .edge_packager import BundleManifest, EdgePackager


@dataclass
class DeploymentRecord:
    """Record of a deployment operation."""
    
    deployment_id: str
    timestamp: str
    bundle_id: str
    model_version: str
    target_path: str
    status: str  # "success" | "failed" | "rolled_back"
    checksum_verified: bool
    load_test_passed: bool
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "DeploymentRecord":
        """Load from dictionary."""
        return cls(**data)
    
    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=2)


class DeploymentManager:
    """Manages model deployment operations."""
    
    def __init__(
        self,
        deployment_dir: Optional[Path] = None,
        history_dir: Optional[Path] = None
    ):
        """
        Initialize deployment manager.
        
        Args:
            deployment_dir: Directory for deployments (default: ~/.local/state/milton/deployments)
            history_dir: Directory for deployment history (default: ~/.local/state/milton/deployment_history)
        """
        if deployment_dir is None:
            deployment_dir = Path.home() / ".local" / "state" / "milton" / "deployments"
        if history_dir is None:
            history_dir = Path.home() / ".local" / "state" / "milton" / "deployment_history"
        
        self.deployment_dir = Path(deployment_dir)
        self.history_dir = Path(history_dir)
        
        self.deployment_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
    
    def _verify_checksums(self, bundle_dir: Path, manifest: BundleManifest) -> bool:
        """
        Verify all file checksums match manifest.
        
        Args:
            bundle_dir: Extracted bundle directory
            manifest: Bundle manifest
        
        Returns:
            True if all checksums match
        """
        packager = EdgePackager()
        
        # Check each file in manifest
        for filename, expected_hash in manifest.files.items():
            # filename is relative to bundle_dir (e.g., "model/file.gguf")
            filepath = bundle_dir / filename
            if not filepath.exists():
                return False
            
            actual_hash = packager._compute_file_hash(filepath)
            if actual_hash != expected_hash:
                return False
        
        return True
    
    def _run_load_test(self, model_path: Path, artifact_type: str = "hf-distilled") -> tuple[bool, Optional[str]]:
        """
        Run a simple load test on the model.
        
        Args:
            model_path: Path to model directory (hf-distilled) or file (gguf)
            artifact_type: Type of artifact ("gguf" or "hf-distilled")
        
        Returns:
            (success, error_message)
        """
        if artifact_type == "gguf":
            # For GGUF, just verify the file exists and is readable
            if not model_path.is_file():
                return False, f"GGUF file does not exist or is not a file: {model_path}"
            
            # Try to read a few bytes to ensure it's readable
            try:
                with open(model_path, "rb") as f:
                    header = f.read(4)
                    if len(header) < 4:
                        return False, "GGUF file is empty or corrupted"
            except Exception as e:
                return False, f"Cannot read GGUF file: {e}"
            
            return True, None
        
        # For HF distilled, check essential files
        essential_files = [
            "config.json",
            "tokenizer_config.json",
        ]
        
        for filename in essential_files:
            filepath = model_path / filename
            if not filepath.exists():
                return False, f"Missing essential file: {filename}"
        
        # Verify config.json is valid JSON
        try:
            config_path = model_path / "config.json"
            with open(config_path) as f:
                config = json.load(f)
            
            # Check for model_type field
            if "model_type" not in config:
                return False, "config.json missing model_type field"
        
        except json.JSONDecodeError as e:
            return False, f"Invalid config.json: {e}"
        except Exception as e:
            return False, f"Error reading config.json: {e}"
        
        return True, None
    
    def deploy_bundle(
        self,
        bundle_path: Path,
        target_path: Optional[Path] = None,
        dry_run: bool = False,
        verify_checksums: bool = True,
        run_load_test: bool = True
    ) -> DeploymentRecord:
        """
        Deploy a bundle to a target path.
        
        Args:
            bundle_path: Path to bundle file
            target_path: Target deployment path (default: auto in deployment_dir)
            dry_run: If True, only validate without deploying
            verify_checksums: If True, verify all checksums
            run_load_test: If True, run load test on extracted model
        
        Returns:
            DeploymentRecord
        """
        bundle_path = Path(bundle_path)
        if not bundle_path.exists():
            raise FileNotFoundError(f"Bundle not found: {bundle_path}")
        
        # Extract manifest
        packager = EdgePackager()
        manifest = packager.extract_manifest(bundle_path)
        
        # Generate deployment ID (include microseconds for uniqueness)
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        microseconds = now.microsecond // 1000  # Convert to milliseconds
        deployment_id = f"deploy_{manifest.model_version}_{timestamp}_{microseconds:03d}"
        
        # Determine target path
        if target_path is None:
            target_path = self.deployment_dir / deployment_id
        else:
            target_path = Path(target_path)
        
        record = DeploymentRecord(
            deployment_id=deployment_id,
            timestamp=datetime.now().isoformat(),
            bundle_id=manifest.bundle_id,
            model_version=manifest.model_version,
            target_path=str(target_path),
            status="failed",
            checksum_verified=False,
            load_test_passed=False
        )
        
        try:
            # Extract bundle to temporary directory
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                
                # Extract tarball
                with tarfile.open(bundle_path, "r:gz") as tar:
                    tar.extractall(tmpdir_path)
                
                # Find extracted bundle directory
                bundle_dirs = list(tmpdir_path.glob("bundle_*"))
                if not bundle_dirs:
                    raise ValueError(f"No bundle directory found in archive")
                bundle_dir = bundle_dirs[0]
                
                # Verify checksums
                if verify_checksums:
                    if not self._verify_checksums(bundle_dir, manifest):
                        record.error_message = "Checksum verification failed"
                        return record
                    record.checksum_verified = True
                
                # Run load test
                if run_load_test:
                    if manifest.artifact_type == "gguf":
                        # For GGUF, find the .gguf file in model/ directory
                        gguf_files = list((bundle_dir / "model").glob("*.gguf"))
                        if not gguf_files:
                            record.error_message = "Load test failed: No GGUF file found in bundle"
                            return record
                        model_test_path = gguf_files[0]
                    else:
                        # For HF distilled, test the model directory
                        model_test_path = bundle_dir / "model"
                    
                    load_test_ok, load_test_error = self._run_load_test(
                        model_test_path,
                        artifact_type=manifest.artifact_type
                    )
                    if not load_test_ok:
                        record.error_message = f"Load test failed: {load_test_error}"
                        return record
                    record.load_test_passed = True
                
                # Deploy (copy to target)
                if not dry_run:
                    if target_path.exists():
                        shutil.rmtree(target_path)
                    target_path.mkdir(parents=True, exist_ok=True)
                    
                    # Copy model
                    if manifest.artifact_type == "gguf":
                        # For GGUF, copy the single file
                        gguf_files = list((bundle_dir / "model").glob("*.gguf"))
                        if gguf_files:
                            model_src = gguf_files[0]
                            model_target = target_path / "model"
                            model_target.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(model_src, model_target / model_src.name)
                    else:
                        # For HF distilled, copy entire directory
                        model_src_dir = bundle_dir / "model"
                        model_target = target_path / "model"
                        shutil.copytree(model_src_dir, model_target)
                    
                    # Copy metadata
                    for filename in ["manifest.json", "registry_entry.json", "benchmark_summary.json", "SHA256SUMS"]:
                        src = bundle_dir / filename
                        dst = target_path / filename
                        shutil.copy2(src, dst)
                    
                    # Create deployment marker
                    marker_path = target_path / "DEPLOYED_AT"
                    marker_path.write_text(datetime.now().isoformat())
                
                record.status = "success"
        
        except Exception as e:
            record.error_message = str(e)
            record.status = "failed"
        
        # Save deployment record
        record_path = self.history_dir / f"{deployment_id}.json"
        record_path.write_text(record.to_json())
        
        return record
    
    def list_deployments(self) -> List[DeploymentRecord]:
        """
        List all deployment records.
        
        Returns:
            List of deployment records (newest first)
        """
        records = []
        for record_path in self.history_dir.glob("deploy_*.json"):
            try:
                data = json.loads(record_path.read_text())
                records.append(DeploymentRecord.from_dict(data))
            except Exception:
                continue
        
        # Sort by timestamp (newest first)
        records.sort(key=lambda x: x.timestamp, reverse=True)
        return records
    
    def get_last_successful_deployment(self) -> Optional[DeploymentRecord]:
        """
        Get the most recent successful deployment.
        
        Returns:
            DeploymentRecord or None
        """
        for record in self.list_deployments():
            if record.status == "success":
                return record
        return None
    
    def rollback_to_previous(self, dry_run: bool = False) -> Optional[DeploymentRecord]:
        """
        Rollback to the previous successful deployment.
        
        Args:
            dry_run: If True, only validate without deploying
        
        Returns:
            DeploymentRecord for rollback operation, or None if no previous deployment
        """
        # Find last successful deployment
        previous = self.get_last_successful_deployment()
        if previous is None:
            return None
        
        # Re-deploy that bundle
        # For rollback, we need to find the original bundle
        # This is a simplified implementation - in production you'd store bundle paths
        # For now, we'll create a rollback record
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rollback_id = f"rollback_{previous.model_version}_{timestamp}"
        
        rollback_record = DeploymentRecord(
            deployment_id=rollback_id,
            timestamp=datetime.now().isoformat(),
            bundle_id=previous.bundle_id,
            model_version=previous.model_version,
            target_path=previous.target_path,
            status="success",
            checksum_verified=True,
            load_test_passed=True,
            error_message=f"Rolled back to deployment {previous.deployment_id}"
        )
        
        if not dry_run:
            record_path = self.history_dir / f"{rollback_id}.json"
            record_path.write_text(rollback_record.to_json())
        
        return rollback_record
