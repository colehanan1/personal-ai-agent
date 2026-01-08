"""
Unit tests for model registry management.

Tests:
- Registry loading and saving
- Adapter lookup operations
- Status transitions
- Promotion workflows
- Rollback functionality
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

from scripts.promote_adapter import AdapterRegistry


@pytest.fixture
def temp_registry(tmp_path):
    """Create a temporary registry file for testing."""
    registry_path = tmp_path / "registry.json"

    registry_data = {
        "version": "1.0",
        "base_model": {
            "name": "Llama-3.1-8B-Instruct-HF",
            "path": "/path/to/model"
        },
        "adapters": [
            {
                "run_id": "lora_20260101_120000",
                "status": "archived",
                "created_at": "2026-01-01T12:00:00Z",
                "archived_at": "2026-01-05T10:00:00Z"
            },
            {
                "run_id": "lora_20260105_140000",
                "status": "production",
                "created_at": "2026-01-05T14:00:00Z",
                "promoted_at": "2026-01-05T15:00:00Z"
            },
            {
                "run_id": "lora_20260106_090000",
                "status": "candidate",
                "created_at": "2026-01-06T09:00:00Z",
                "promoted_at": "2026-01-06T09:30:00Z"
            }
        ]
    }

    with registry_path.open("w") as f:
        json.dump(registry_data, f, indent=2)

    return registry_path


class TestRegistryLoading:
    """Test registry file operations."""

    def test_loads_registry(self, temp_registry):
        """Should load existing registry."""
        registry = AdapterRegistry.load(temp_registry)

        assert registry["version"] == "1.0"
        assert len(registry["adapters"]) == 3

    def test_fails_on_missing_registry(self, tmp_path):
        """Should raise FileNotFoundError for missing registry."""
        nonexistent = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            AdapterRegistry.load(nonexistent)

    def test_saves_registry(self, temp_registry):
        """Should save registry with modifications."""
        reg = AdapterRegistry(temp_registry)

        # Modify
        reg.registry["adapters"].append({
            "run_id": "new_adapter",
            "status": "training"
        })

        # Save
        reg.save()

        # Reload and verify
        reloaded = AdapterRegistry.load(temp_registry)
        assert len(reloaded["adapters"]) == 4
        assert reloaded["adapters"][-1]["run_id"] == "new_adapter"


class TestAdapterLookup:
    """Test adapter query operations."""

    def test_gets_adapter_by_run_id(self, temp_registry):
        """Should find adapter by run_id."""
        reg = AdapterRegistry(temp_registry)

        adapter = reg.get_adapter("lora_20260105_140000")

        assert adapter is not None
        assert adapter["status"] == "production"

    def test_returns_none_for_missing_adapter(self, temp_registry):
        """Should return None for non-existent adapter."""
        reg = AdapterRegistry(temp_registry)

        adapter = reg.get_adapter("nonexistent")

        assert adapter is None

    def test_gets_adapters_by_status(self, temp_registry):
        """Should filter adapters by status."""
        reg = AdapterRegistry(temp_registry)

        archived = reg.get_adapters_by_status("archived")
        production = reg.get_adapters_by_status("production")
        candidate = reg.get_adapters_by_status("candidate")

        assert len(archived) == 1
        assert len(production) == 1
        assert len(candidate) == 1

    def test_gets_production_adapter(self, temp_registry):
        """Should get current production adapter."""
        reg = AdapterRegistry(temp_registry)

        prod = reg.get_production_adapter()

        assert prod is not None
        assert prod["run_id"] == "lora_20260105_140000"

    def test_returns_none_when_no_production(self, tmp_path):
        """Should return None when no production adapter exists."""
        registry_path = tmp_path / "registry.json"
        registry_data = {
            "version": "1.0",
            "base_model": {"name": "test", "path": "/path"},
            "adapters": [
                {"run_id": "test", "status": "candidate"}
            ]
        }
        with registry_path.open("w") as f:
            json.dump(registry_data, f)

        reg = AdapterRegistry(registry_path)
        prod = reg.get_production_adapter()

        assert prod is None


class TestPromotionWorkflows:
    """Test adapter promotion logic."""

    def test_promotes_to_candidate(self, temp_registry):
        """Should update status to candidate."""
        reg = AdapterRegistry(temp_registry)

        # Create new adapter in training status
        reg.registry["adapters"].append({
            "run_id": "test_adapter",
            "status": "training"
        })

        reg.promote_to_candidate("test_adapter")

        adapter = reg.get_adapter("test_adapter")
        assert adapter["status"] == "candidate"
        assert "promoted_at" in adapter

    def test_skips_if_already_candidate(self, temp_registry):
        """Should not error if already candidate."""
        reg = AdapterRegistry(temp_registry)

        # This should not raise
        reg.promote_to_candidate("lora_20260106_090000")

        adapter = reg.get_adapter("lora_20260106_090000")
        assert adapter["status"] == "candidate"

    def test_promotes_to_production_archives_previous(self, temp_registry):
        """Should archive current production when promoting new."""
        reg = AdapterRegistry(temp_registry)

        old_production_id = reg.get_production_adapter()["run_id"]

        reg.promote_to_production("lora_20260106_090000", force=True)

        # Check new production
        new_prod = reg.get_production_adapter()
        assert new_prod["run_id"] == "lora_20260106_090000"

        # Check old production is archived
        old_adapter = reg.get_adapter(old_production_id)
        assert old_adapter["status"] == "archived"
        assert "archived_at" in old_adapter

    def test_promotes_when_no_previous_production(self, tmp_path):
        """Should promote even when no previous production exists."""
        registry_path = tmp_path / "registry.json"
        registry_data = {
            "version": "1.0",
            "base_model": {"name": "test", "path": "/path"},
            "adapters": [
                {"run_id": "test", "status": "candidate"}
            ]
        }
        with registry_path.open("w") as f:
            json.dump(registry_data, f)

        reg = AdapterRegistry(registry_path)
        reg.promote_to_production("test", force=True)

        adapter = reg.get_adapter("test")
        assert adapter["status"] == "production"


class TestArchiving:
    """Test adapter archiving."""

    def test_archives_adapter(self, temp_registry):
        """Should update status to archived."""
        reg = AdapterRegistry(temp_registry)

        reg.archive_adapter("lora_20260106_090000")

        adapter = reg.get_adapter("lora_20260106_090000")
        assert adapter["status"] == "archived"
        assert "archived_at" in adapter


class TestRollback:
    """Test rollback functionality."""

    def test_rollback_to_previous(self, temp_registry):
        """Should restore most recent archived adapter."""
        reg = AdapterRegistry(temp_registry)

        # Rollback (should promote most recent archived: lora_20260101_120000)
        reg.rollback_to_previous()

        # Check it's now production
        prod = reg.get_production_adapter()
        assert prod["run_id"] == "lora_20260101_120000"
        assert prod["status"] == "production"

    def test_rollback_fails_when_no_archived(self, tmp_path):
        """Should raise error when no archived adapters exist."""
        registry_path = tmp_path / "registry.json"
        registry_data = {
            "version": "1.0",
            "base_model": {"name": "test", "path": "/path"},
            "adapters": [
                {"run_id": "test", "status": "production"}
            ]
        }
        with registry_path.open("w") as f:
            json.dump(registry_data, f)

        reg = AdapterRegistry(registry_path)

        with pytest.raises(ValueError, match="No archived adapters"):
            reg.rollback_to_previous()


class TestListAdapters:
    """Test adapter listing functionality."""

    def test_lists_adapters(self, temp_registry, capsys):
        """Should print adapter list."""
        reg = AdapterRegistry(temp_registry)

        reg.list_adapters()

        captured = capsys.readouterr()
        assert "lora_20260101_120000" in captured.out
        assert "lora_20260105_140000" in captured.out
        assert "production ★" in captured.out  # Production marker

    def test_handles_empty_registry(self, tmp_path, capsys):
        """Should handle empty adapter list."""
        registry_path = tmp_path / "registry.json"
        registry_data = {
            "version": "1.0",
            "base_model": {"name": "test", "path": "/path"},
            "adapters": []
        }
        with registry_path.open("w") as f:
            json.dump(registry_data, f)

        reg = AdapterRegistry(registry_path)
        reg.list_adapters()

        captured = capsys.readouterr()
        assert "No adapters in registry" in captured.out
