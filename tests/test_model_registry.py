"""
Unit tests for model registry management.

Tests:
- Registry loading and saving
- Model registration
- Version lookup operations
- Active model management
- Rollback functionality
- Model comparison
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from training.model_registry import ModelRegistry, ModelRegistryEntry


@pytest.fixture
def temp_registry_dir(tmp_path):
    """Create a temporary directory for registry testing."""
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)
    return models_dir


@pytest.fixture
def populated_registry(temp_registry_dir):
    """Create a registry with test entries."""
    registry = ModelRegistry(
        models_dir=temp_registry_dir,
    )
    
    # Add test models
    registry.register_model(
        version="v3.1-week01",
        base_model="llama-3.1-8b",
        model_path=temp_registry_dir / "model1",
        metrics={"perplexity": 12.5, "quality": 0.85},
        quantization="4bit",
    )
    
    registry.register_model(
        version="v3.1-week02",
        base_model="llama-3.1-8b",
        model_path=temp_registry_dir / "model2",
        metrics={"perplexity": 11.8, "quality": 0.88},
        quantization="4bit",
        set_active=True,
    )
    
    registry.register_model(
        version="v3.1-week03",
        base_model="llama-3.1-8b",
        model_path=temp_registry_dir / "model3",
        metrics={"perplexity": 11.2, "quality": 0.91},
        quantization="8bit",
    )
    
    return registry


class TestRegistryBasics:
    """Test basic registry operations."""
    
    def test_creates_empty_registry(self, temp_registry_dir):
        """Should create a new empty registry."""
        registry = ModelRegistry(models_dir=temp_registry_dir)
        
        assert len(registry.entries) == 0
        assert registry.registry_path.exists()
    
    def test_loads_existing_registry(self, populated_registry, temp_registry_dir):
        """Should load existing registry from disk."""
        # Create a new registry instance pointing to same path
        new_registry = ModelRegistry(models_dir=temp_registry_dir)
        
        assert len(new_registry.entries) == 3
    
    def test_persists_changes(self, populated_registry, temp_registry_dir):
        """Should save changes to disk."""
        populated_registry.register_model(
            version="v3.1-week04",
            base_model="llama-3.1-8b",
            model_path=temp_registry_dir / "model4",
            metrics={"perplexity": 10.9},
        )
        
        # Reload and verify
        new_registry = ModelRegistry(models_dir=temp_registry_dir)
        assert len(new_registry.entries) == 4


class TestModelRegistration:
    """Test model registration."""
    
    def test_registers_model(self, temp_registry_dir):
        """Should register a new model."""
        registry = ModelRegistry(models_dir=temp_registry_dir)
        
        model_path = temp_registry_dir / "test_model"
        entry = registry.register_model(
            version="v1.0",
            base_model="test-model",
            model_path=model_path,
            metrics={"test": 123},
        )
        
        assert entry.version == "v1.0"
        assert entry.base_model == "test-model"
        assert not entry.active
    
    def test_updates_existing_version(self, populated_registry):
        """Should update if version already exists."""
        populated_registry.register_model(
            version="v3.1-week01",  # Duplicate
            base_model="llama-3.1-8b",
            model_path=populated_registry.models_dir / "updated",
            metrics={"perplexity": 10.0},
        )
        
        # Should still have 3 entries (not 4)
        assert len(populated_registry.entries) == 3
        
        # Should have updated metrics
        model = populated_registry.get_model("v3.1-week01")
        assert model.metrics["perplexity"] == 10.0
    
    def test_registers_with_metadata(self, temp_registry_dir):
        """Should store all metadata fields."""
        registry = ModelRegistry(models_dir=temp_registry_dir)
        
        entry = registry.register_model(
            version="v1.0",
            base_model="test",
            model_path=temp_registry_dir / "model",
            metrics={"key": "value"},
            distilled_from="adapter-123",
            quantization="4bit",
            commit_hash="abc123",
        )
        
        assert entry.distilled_from == "adapter-123"
        assert entry.quantization == "4bit"
        assert entry.commit_hash == "abc123"


class TestModelRetrieval:
    """Test model lookup operations."""
    
    def test_gets_model_by_version(self, populated_registry):
        """Should find model by version."""
        model = populated_registry.get_model("v3.1-week02")
        
        assert model is not None
        assert model.version == "v3.1-week02"
    
    def test_returns_none_for_missing(self, populated_registry):
        """Should return None for non-existent version."""
        model = populated_registry.get_model("nonexistent")
        
        assert model is None
    
    def test_gets_latest_model(self, populated_registry):
        """Should return most recent model."""
        latest = populated_registry.get_latest()
        
        assert latest is not None
        # Should be week03 (most recent timestamp)
    
    def test_gets_active_model(self, populated_registry):
        """Should return currently active model."""
        active = populated_registry.get_active()
        
        assert active is not None
        assert active.version == "v3.1-week02"
        assert active.active is True
    
    def test_gets_last_good_model(self, populated_registry):
        """Should return last known good model."""
        # Activate a new model (should mark v3.1-week02 as last_good)
        populated_registry.activate_model("v3.1-week03")
        
        last_good = populated_registry.get_last_good()
        assert last_good is not None
        assert last_good.version == "v3.1-week02"


class TestModelActivation:
    """Test model activation."""
    
    def test_activates_model(self, populated_registry):
        """Should set model as active."""
        result = populated_registry.activate_model("v3.1-week03")
        
        assert result is True
        
        active = populated_registry.get_active()
        assert active.version == "v3.1-week03"
    
    def test_deactivates_previous(self, populated_registry):
        """Should deactivate previous active model."""
        populated_registry.activate_model("v3.1-week03")
        
        week02 = populated_registry.get_model("v3.1-week02")
        assert week02.active is False
    
    def test_marks_previous_as_last_good(self, populated_registry):
        """Should mark previous active as last_good."""
        populated_registry.activate_model("v3.1-week03")
        
        week02 = populated_registry.get_model("v3.1-week02")
        assert week02.last_good is True
    
    def test_fails_for_nonexistent(self, populated_registry):
        """Should return False for non-existent version."""
        result = populated_registry.activate_model("nonexistent")
        
        assert result is False


class TestRollback:
    """Test rollback functionality."""
    
    def test_rollback_to_last_good(self, populated_registry):
        """Should rollback to last known good model."""
        # Activate week03, making week02 last_good
        populated_registry.activate_model("v3.1-week03")
        
        # Now rollback
        rolled_back = populated_registry.rollback_model()
        
        assert rolled_back is not None
        assert rolled_back.version == "v3.1-week02"
        assert rolled_back.active is True
    
    def test_rollback_deactivates_current(self, populated_registry):
        """Should deactivate current active model."""
        populated_registry.activate_model("v3.1-week03")
        populated_registry.rollback_model()
        
        week03 = populated_registry.get_model("v3.1-week03")
        assert week03.active is False
    
    def test_rollback_fails_without_last_good(self, temp_registry_dir):
        """Should return None when no last_good exists."""
        registry = ModelRegistry(models_dir=temp_registry_dir)
        
        registry.register_model(
            version="v1.0",
            base_model="test",
            model_path=temp_registry_dir / "model",
            metrics={},
            set_active=True,
        )
        
        result = registry.rollback_model()
        assert result is None


class TestModelListing:
    """Test model listing and filtering."""
    
    def test_lists_all_models(self, populated_registry):
        """Should list all models."""
        models = populated_registry.list_models()
        
        assert len(models) == 3
    
    def test_filters_by_base_model(self, populated_registry):
        """Should filter by base model."""
        models = populated_registry.list_models(base_model="llama-3.1-8b")
        
        assert len(models) == 3
        
        models = populated_registry.list_models(base_model="nonexistent")
        assert len(models) == 0
    
    def test_filters_by_quantization(self, populated_registry):
        """Should filter by quantization level."""
        models_4bit = populated_registry.list_models(quantization="4bit")
        models_8bit = populated_registry.list_models(quantization="8bit")
        
        assert len(models_4bit) == 2
        assert len(models_8bit) == 1
    
    def test_sorts_by_timestamp(self, populated_registry):
        """Should return models sorted by timestamp (newest first)."""
        models = populated_registry.list_models()
        
        # Timestamps should be in descending order
        timestamps = [m.timestamp for m in models]
        assert timestamps == sorted(timestamps, reverse=True)


class TestModelComparison:
    """Test model comparison functionality."""
    
    def test_compares_models(self, populated_registry):
        """Should compare two models."""
        comparison = populated_registry.compare_models(
            "v3.1-week01",
            "v3.1-week02",
        )
        
        assert comparison["version_a"] == "v3.1-week01"
        assert comparison["version_b"] == "v3.1-week02"
        assert "metrics_delta" in comparison
    
    def test_calculates_metric_deltas(self, populated_registry):
        """Should calculate differences in metrics."""
        comparison = populated_registry.compare_models(
            "v3.1-week01",
            "v3.1-week02",
        )
        
        # week02 perplexity (11.8) - week01 perplexity (12.5) = -0.7
        assert "perplexity" in comparison["metrics_delta"]
        assert comparison["metrics_delta"]["perplexity"] < 0  # Improved
    
    def test_handles_missing_models(self, populated_registry):
        """Should return empty dict for missing models."""
        comparison = populated_registry.compare_models(
            "v3.1-week01",
            "nonexistent",
        )
        
        assert comparison == {}


class TestRegistryStats:
    """Test registry statistics."""
    
    def test_gets_stats(self, populated_registry):
        """Should return registry statistics."""
        stats = populated_registry.get_stats()
        
        assert stats["total_models"] == 3
        assert stats["active_model"] == "v3.1-week02"
        assert "quantization_breakdown" in stats
        assert "base_model_breakdown" in stats
    
    def test_quantization_breakdown(self, populated_registry):
        """Should count models by quantization."""
        stats = populated_registry.get_stats()
        
        assert stats["quantization_breakdown"]["4bit"] == 2
        assert stats["quantization_breakdown"]["8bit"] == 1
