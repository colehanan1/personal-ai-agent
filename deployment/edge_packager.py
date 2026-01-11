"""
Edge bundle packager for Milton models.

Creates a self-contained bundle with:
- Model files
- Registry metadata
- Benchmark summary
- SHA256 checksums
- Manifest
"""

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class BundleManifest:
    """Manifest for an edge bundle."""
    
    bundle_id: str
    created_at: str
    model_version: str
    model_path: str
    artifact_type: str  # "gguf" or "hf-distilled"
    registry_entry: Dict
    benchmark_summary: Dict
    files: Dict[str, str]  # filename -> sha256
    total_size_bytes: int
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "BundleManifest":
        """Load from dictionary."""
        return cls(**data)
    
    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "BundleManifest":
        """Deserialize from JSON."""
        return cls.from_dict(json.loads(json_str))


class EdgePackager:
    """Packages models into edge bundles."""
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize packager.
        
        Args:
            output_dir: Directory for output bundles (default: ~/.local/state/milton/bundles)
        """
        if output_dir is None:
            output_dir = Path.home() / ".local" / "state" / "milton" / "bundles"
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _compute_file_hash(self, filepath: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def _compute_dir_hashes(self, dirpath: Path) -> Dict[str, str]:
        """Compute SHA256 hashes for all files in directory."""
        hashes = {}
        for root, dirs, files in os.walk(dirpath):
            for filename in files:
                filepath = Path(root) / filename
                rel_path = filepath.relative_to(dirpath)
                hashes[str(rel_path)] = self._compute_file_hash(filepath)
        return hashes
    
    def _get_dir_size(self, dirpath: Path) -> int:
        """Get total size of directory in bytes."""
        total_size = 0
        for root, dirs, files in os.walk(dirpath):
            for filename in files:
                filepath = Path(root) / filename
                total_size += filepath.stat().st_size
        return total_size
    
    def create_bundle(
        self,
        model_path: Path,
        registry_entry: Dict,
        benchmark_summary: Dict,
        artifact_type: str = "gguf",
        bundle_name: Optional[str] = None
    ) -> Path:
        """
        Create an edge bundle.
        
        Args:
            model_path: Path to model file (GGUF) or directory (HF)
            registry_entry: Registry metadata for the model
            benchmark_summary: Benchmark results summary
            artifact_type: "gguf" (single file) or "hf-distilled" (directory)
            bundle_name: Custom bundle name (default: auto-generated)
        
        Returns:
            Path to created bundle (.tar.gz)
        """
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"Model path does not exist: {model_path}")
        
        # Validate artifact type matches path type
        if artifact_type == "gguf":
            if not model_path.is_file():
                raise ValueError(f"artifact_type='gguf' requires a file, got directory: {model_path}")
        elif artifact_type == "hf-distilled":
            if not model_path.is_dir():
                raise ValueError(f"artifact_type='hf-distilled' requires a directory, got file: {model_path}")
        else:
            raise ValueError(f"Invalid artifact_type: {artifact_type}. Must be 'gguf' or 'hf-distilled'")
        
        # Generate bundle ID and name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_version = registry_entry.get("version", "unknown")
        bundle_id = f"bundle_{model_version}_{timestamp}"
        
        if bundle_name is None:
            bundle_name = f"milton_edge_bundle_{model_version}_{timestamp}.tar.gz"
        
        # Create temporary directory for bundle contents
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_dir = Path(tmpdir) / bundle_id
            bundle_dir.mkdir()
            
            # Handle model files based on artifact type
            if artifact_type == "gguf":
                # Single GGUF file - just copy it
                model_dest = bundle_dir / "model"
                model_dest.mkdir()
                gguf_dest = model_dest / model_path.name
                shutil.copy2(model_path, gguf_dest)
                
                # Compute hash for single file (fast)
                file_hashes = {
                    f"model/{model_path.name}": self._compute_file_hash(gguf_dest)
                }
                total_size = gguf_dest.stat().st_size
            
            else:  # hf-distilled
                # Copy entire directory (slow)
                model_dest = bundle_dir / "model"
                shutil.copytree(model_path, model_dest)
                
                # Compute file hashes for all files (relative to bundle_dir)
                raw_hashes = self._compute_dir_hashes(model_dest)
                # Prefix with "model/" to make paths relative to bundle_dir
                file_hashes = {
                    f"model/{filename}": hash_val
                    for filename, hash_val in raw_hashes.items()
                }
                total_size = self._get_dir_size(model_dest)
            
            # Create manifest
            manifest = BundleManifest(
                bundle_id=bundle_id,
                created_at=datetime.now().isoformat(),
                model_version=model_version,
                model_path=str(model_path),
                artifact_type=artifact_type,
                registry_entry=registry_entry,
                benchmark_summary=benchmark_summary,
                files=file_hashes,
                total_size_bytes=total_size
            )
            
            # Write manifest
            manifest_path = bundle_dir / "manifest.json"
            manifest_path.write_text(manifest.to_json())
            
            # Write registry snippet
            registry_path = bundle_dir / "registry_entry.json"
            registry_path.write_text(json.dumps(registry_entry, indent=2))
            
            # Write benchmark summary
            benchmark_path = bundle_dir / "benchmark_summary.json"
            benchmark_path.write_text(json.dumps(benchmark_summary, indent=2))
            
            # Compute checksums for metadata files
            metadata_hashes = {
                "manifest.json": self._compute_file_hash(manifest_path),
                "registry_entry.json": self._compute_file_hash(registry_path),
                "benchmark_summary.json": self._compute_file_hash(benchmark_path),
            }
            
            # Write checksums file
            all_hashes = {**file_hashes, **metadata_hashes}
            checksums_path = bundle_dir / "SHA256SUMS"
            with open(checksums_path, "w") as f:
                for filename, hash_val in sorted(all_hashes.items()):
                    f.write(f"{hash_val}  {filename}\n")
            
            # Create tarball
            output_path = self.output_dir / bundle_name
            with tarfile.open(output_path, "w:gz") as tar:
                tar.add(bundle_dir, arcname=bundle_id)
        
        return output_path
    
    def extract_manifest(self, bundle_path: Path) -> BundleManifest:
        """
        Extract manifest from bundle without unpacking entire archive.
        
        Args:
            bundle_path: Path to bundle file
        
        Returns:
            BundleManifest
        """
        bundle_path = Path(bundle_path)
        if not bundle_path.exists():
            raise FileNotFoundError(f"Bundle not found: {bundle_path}")
        
        with tarfile.open(bundle_path, "r:gz") as tar:
            # Find manifest file
            members = tar.getmembers()
            manifest_member = None
            for member in members:
                if member.name.endswith("/manifest.json"):
                    manifest_member = member
                    break
            
            if manifest_member is None:
                raise ValueError(f"No manifest.json found in bundle: {bundle_path}")
            
            # Extract and parse manifest
            manifest_file = tar.extractfile(manifest_member)
            if manifest_file is None:
                raise ValueError(f"Could not extract manifest from bundle: {bundle_path}")
            
            manifest_data = json.loads(manifest_file.read().decode("utf-8"))
            return BundleManifest.from_dict(manifest_data)
    
    def list_bundles(self) -> List[Dict]:
        """
        List all available bundles.
        
        Returns:
            List of bundle info dictionaries
        """
        bundles = []
        for bundle_path in self.output_dir.glob("*.tar.gz"):
            try:
                manifest = self.extract_manifest(bundle_path)
                bundles.append({
                    "path": str(bundle_path),
                    "bundle_id": manifest.bundle_id,
                    "model_version": manifest.model_version,
                    "created_at": manifest.created_at,
                    "size_bytes": bundle_path.stat().st_size,
                })
            except Exception as e:
                # Skip invalid bundles
                continue
        
        # Sort by creation time (newest first)
        bundles.sort(key=lambda x: x["created_at"], reverse=True)
        return bundles
