"""
Tests for PEFT adapter validation.

Ensures only valid PEFT adapters can be registered and activated.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from training.adapter_manager import AdapterManager, validate_peft_adapter_dir


class TestPeftAdapterValidation:
    """Test PEFT adapter validation logic."""
    
    def test_validate_missing_directory(self, tmp_path):
        """Should fail if adapter directory doesn't exist."""
        nonexistent = tmp_path / "nonexistent"
        
        with pytest.raises(RuntimeError, match="does not exist"):
            validate_peft_adapter_dir(nonexistent)
    
    def test_validate_missing_config(self, tmp_path):
        """Should fail if adapter_config.json is missing."""
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        
        with pytest.raises(RuntimeError, match="Missing adapter_config.json"):
            validate_peft_adapter_dir(adapter_dir)
    
    def test_validate_missing_peft_type(self, tmp_path):
        """Should fail if adapter_config.json missing 'peft_type' key."""
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        
        # Create invalid config (like our test adapter)
        config_path = adapter_dir / "adapter_config.json"
        config_path.write_text(json.dumps({"test": True}))
        
        with pytest.raises(RuntimeError, match="Missing 'peft_type'"):
            validate_peft_adapter_dir(adapter_dir)
    
    def test_validate_missing_weights(self, tmp_path):
        """Should fail if adapter weights file is missing."""
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        
        # Create valid config but no weights
        config_path = adapter_dir / "adapter_config.json"
        config_path.write_text(json.dumps({
            "peft_type": "LORA",
            "base_model_name_or_path": "test",
        }))
        
        with pytest.raises(RuntimeError, match="Missing adapter weights"):
            validate_peft_adapter_dir(adapter_dir)
    
    def test_validate_valid_adapter_safetensors(self, tmp_path):
        """Should pass with valid adapter (safetensors)."""
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        
        # Create valid config
        config_path = adapter_dir / "adapter_config.json"
        config_path.write_text(json.dumps({
            "peft_type": "LORA",
            "base_model_name_or_path": "test",
        }))
        
        # Create weights file
        weights_path = adapter_dir / "adapter_model.safetensors"
        weights_path.write_text("dummy weights")
        
        # Should not raise
        validate_peft_adapter_dir(adapter_dir)
    
    def test_validate_valid_adapter_bin(self, tmp_path):
        """Should pass with valid adapter (bin)."""
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        
        # Create valid config
        config_path = adapter_dir / "adapter_config.json"
        config_path.write_text(json.dumps({
            "peft_type": "LORA",
            "base_model_name_or_path": "test",
        }))
        
        # Create weights file (bin format)
        weights_path = adapter_dir / "adapter_model.bin"
        weights_path.write_text("dummy weights")
        
        # Should not raise
        validate_peft_adapter_dir(adapter_dir)


class TestAdapterManagerValidation:
    """Test AdapterManager validates adapters."""
    
    def test_register_invalid_adapter_fails(self, tmp_path):
        """Should not register an adapter with missing peft_type."""
        adapter_dir = tmp_path / "adapters"
        adapter_dir.mkdir()
        
        invalid_adapter = adapter_dir / "invalid"
        invalid_adapter.mkdir()
        
        # Create invalid config
        config_path = invalid_adapter / "adapter_config.json"
        config_path.write_text(json.dumps({"test": True}))
        
        manager = AdapterManager(adapters_dir=adapter_dir)
        
        with pytest.raises(RuntimeError, match="Missing 'peft_type'"):
            manager.register_adapter(
                name="invalid",
                adapter_path=invalid_adapter,
                quality_score=0.8,
            )
    
    def test_register_valid_adapter_succeeds(self, tmp_path):
        """Should successfully register a valid adapter."""
        adapter_dir = tmp_path / "adapters"
        adapter_dir.mkdir()
        
        valid_adapter = adapter_dir / "valid"
        valid_adapter.mkdir()
        
        # Create valid config
        config_path = valid_adapter / "adapter_config.json"
        config_path.write_text(json.dumps({
            "peft_type": "LORA",
            "base_model_name_or_path": "test",
        }))
        
        # Create weights
        weights_path = valid_adapter / "adapter_model.safetensors"
        weights_path.write_text("dummy")
        
        manager = AdapterManager(adapters_dir=adapter_dir)
        
        # Should not raise
        info = manager.register_adapter(
            name="valid",
            adapter_path=valid_adapter,
            quality_score=0.8,
        )
        
        assert info.name == "valid"
    
    def test_activate_invalid_adapter_fails(self, tmp_path):
        """Should not activate an invalid adapter."""
        adapter_dir = tmp_path / "adapters"
        adapter_dir.mkdir()
        
        # Create adapter dir
        test_adapter = adapter_dir / "test"
        test_adapter.mkdir()
        
        # Create valid config and weights initially
        config_path = test_adapter / "adapter_config.json"
        config_path.write_text(json.dumps({
            "peft_type": "LORA",
            "base_model_name_or_path": "test",
        }))
        
        weights_path = test_adapter / "adapter_model.safetensors"
        weights_path.write_text("dummy")
        
        manager = AdapterManager(adapters_dir=adapter_dir)
        manager.register_adapter(
            name="test",
            adapter_path=test_adapter,
            quality_score=0.8,
        )
        
        # Now corrupt the adapter (remove weights)
        weights_path.unlink()
        
        # Activation should fail
        with pytest.raises(RuntimeError, match="Missing adapter weights"):
            manager.activate("test")
    
    def test_current_adapter_validates(self, tmp_path):
        """Should validate when getting current adapter."""
        adapter_dir = tmp_path / "adapters"
        adapter_dir.mkdir()
        
        # Create valid adapter
        test_adapter = adapter_dir / "test"
        test_adapter.mkdir()
        
        config_path = test_adapter / "adapter_config.json"
        config_path.write_text(json.dumps({
            "peft_type": "LORA",
            "base_model_name_or_path": "test",
        }))
        
        weights_path = test_adapter / "adapter_model.safetensors"
        weights_path.write_text("dummy")
        
        manager = AdapterManager(adapters_dir=adapter_dir)
        manager.register_adapter(
            name="test",
            adapter_path=test_adapter,
            quality_score=0.8,
            auto_activate=True,
        )
        
        # Should work fine
        current = manager.current_adapter()
        assert current is not None
        assert current.name == "test"
        
        # Now corrupt the adapter
        weights_path.unlink()
        
        # Should fail when trying to get current adapter
        with pytest.raises(RuntimeError, match="Active adapter 'test' is invalid"):
            manager.current_adapter()
