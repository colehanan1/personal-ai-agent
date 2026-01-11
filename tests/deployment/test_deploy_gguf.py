"""
Tests for GGUF-first deployment.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from scripts.deploy_best_model import get_artifact_path_from_registry


class TestGetArtifactPath:
    """Tests for get_artifact_path_from_registry function."""
    
    def test_gguf_artifact_success(self):
        """Test successful GGUF artifact extraction."""
        # Create temp GGUF file
        with tempfile.NamedTemporaryFile(suffix=".gguf", delete=False) as f:
            gguf_path = Path(f.name)
            f.write(b"fake_gguf")
        
        try:
            # Mock registry entry
            mock_entry = Mock()
            mock_entry.version = "v1.0.0"
            mock_entry.model_path = "/some/dir"
            mock_entry.metrics = {
                "compression": {
                    "gguf_path": str(gguf_path)
                }
            }
            
            # Mock registry
            mock_registry = Mock()
            mock_registry.list_models.return_value = [mock_entry]
            
            # Test
            artifact_path, artifact_type = get_artifact_path_from_registry(
                "v1.0.0", mock_registry, "gguf"
            )
            
            assert artifact_path == gguf_path
            assert artifact_type == "gguf"
        
        finally:
            gguf_path.unlink()
    
    def test_gguf_missing_in_registry(self):
        """Test GGUF missing from registry fails loudly."""
        # Mock registry entry without GGUF
        mock_entry = Mock()
        mock_entry.version = "v1.0.0"
        mock_entry.model_path = "/some/dir"
        mock_entry.metrics = {}  # No compression field
        
        mock_registry = Mock()
        mock_registry.list_models.return_value = [mock_entry]
        
        # Should raise RuntimeError with clear message
        with pytest.raises(RuntimeError) as excinfo:
            get_artifact_path_from_registry("v1.0.0", mock_registry, "gguf")
        
        error_msg = str(excinfo.value)
        assert "No GGUF found" in error_msg
        assert "quantization" in error_msg.lower()
        assert "--artifact hf-distilled" in error_msg
    
    def test_gguf_file_missing(self):
        """Test GGUF path in registry but file doesn't exist."""
        # Mock registry with non-existent GGUF path
        mock_entry = Mock()
        mock_entry.version = "v1.0.0"
        mock_entry.model_path = "/some/dir"
        mock_entry.metrics = {
            "compression": {
                "gguf_path": "/nonexistent/model.gguf"
            }
        }
        
        mock_registry = Mock()
        mock_registry.list_models.return_value = [mock_entry]
        
        # Should raise RuntimeError
        with pytest.raises(RuntimeError) as excinfo:
            get_artifact_path_from_registry("v1.0.0", mock_registry, "gguf")
        
        error_msg = str(excinfo.value)
        assert "does not exist" in error_msg
        assert "/nonexistent/model.gguf" in error_msg
    
    def test_gguf_path_is_directory(self):
        """Test GGUF path points to directory instead of file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock registry with directory instead of file
            mock_entry = Mock()
            mock_entry.version = "v1.0.0"
            mock_entry.model_path = "/some/dir"
            mock_entry.metrics = {
                "compression": {
                    "gguf_path": tmpdir
                }
            }
            
            mock_registry = Mock()
            mock_registry.list_models.return_value = [mock_entry]
            
            # Should raise RuntimeError
            with pytest.raises(RuntimeError) as excinfo:
                get_artifact_path_from_registry("v1.0.0", mock_registry, "gguf")
            
            error_msg = str(excinfo.value)
            assert "not a file" in error_msg
    
    def test_hf_distilled_artifact(self):
        """Test HF distilled artifact extraction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock registry entry
            mock_entry = Mock()
            mock_entry.version = "v1.0.0"
            mock_entry.model_path = tmpdir
            
            mock_registry = Mock()
            mock_registry.list_models.return_value = [mock_entry]
            
            # Test
            artifact_path, artifact_type = get_artifact_path_from_registry(
                "v1.0.0", mock_registry, "hf-distilled"
            )
            
            assert artifact_path == Path(tmpdir)
            assert artifact_type == "hf-distilled"
    
    def test_hf_distilled_missing(self):
        """Test HF distilled path doesn't exist."""
        # Mock registry with non-existent path
        mock_entry = Mock()
        mock_entry.version = "v1.0.0"
        mock_entry.model_path = "/nonexistent/dir"
        
        mock_registry = Mock()
        mock_registry.list_models.return_value = [mock_entry]
        
        # Should raise RuntimeError
        with pytest.raises(RuntimeError) as excinfo:
            get_artifact_path_from_registry("v1.0.0", mock_registry, "hf-distilled")
        
        assert "does not exist" in str(excinfo.value)
    
    def test_model_not_in_registry(self):
        """Test model version not found in registry."""
        mock_registry = Mock()
        mock_registry.list_models.return_value = []
        
        # Should raise ValueError
        with pytest.raises(ValueError) as excinfo:
            get_artifact_path_from_registry("v99.99.99", mock_registry, "gguf")
        
        assert "Model not found in registry" in str(excinfo.value)
