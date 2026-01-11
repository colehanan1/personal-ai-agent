"""
Model Registry Module

Tracks evolved models (distilled + quantized) with version control.
Enables rollback, comparison, and deployment management.
"""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from milton_orchestrator.state_paths import resolve_state_dir

logger = logging.getLogger(__name__)


@dataclass
class ModelRegistryEntry:
    """Entry in the model registry."""
    version: str
    base_model: str
    distilled_from: Optional[str]  # LoRA adapter ID
    quantization: Optional[str]  # e.g., "4bit", "8bit"
    model_path: str
    timestamp: str
    metrics: Dict[str, Any]
    active: bool = False
    last_good: bool = False
    commit_hash: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ModelRegistryEntry:
        return cls(**data)


class ModelRegistry:
    """
    Manages versioned registry of evolved models.
    
    Tracks:
    - Distilled models
    - Quantized models
    - Base models + adapter combinations
    - Quality metrics and deployment status
    
    Supports:
    - Version control with metadata
    - Rollback to previous versions
    - Comparison across versions
    - Active model management
    """
    
    def __init__(
        self,
        registry_path: Optional[Path] = None,
        models_dir: Optional[Path] = None,
    ):
        """
        Initialize model registry.
        
        Args:
            registry_path: Path to registry JSON file
            models_dir: Base directory for models
        """
        self.models_dir = models_dir or Path(resolve_state_dir("models"))
        self.registry_path = registry_path or self.models_dir / "registry.json"
        
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._load_registry()
        
        logger.info(f"ModelRegistry initialized: {self.registry_path}")
        logger.info(f"Loaded {len(self.entries)} model entries")
    
    def _load_registry(self):
        """Load registry from disk."""
        if self.registry_path.exists():
            try:
                data = json.loads(self.registry_path.read_text())
                self.entries = [ModelRegistryEntry.from_dict(e) for e in data]
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")
                self.entries = []
        else:
            self.entries = []
            # Create empty registry file
            self._save_registry()
    
    def _save_registry(self):
        """Save registry to disk."""
        try:
            data = [e.to_dict() for e in self.entries]
            self.registry_path.write_text(json.dumps(data, indent=2))
            logger.debug(f"Registry saved: {len(self.entries)} entries")
        except Exception as e:
            logger.error(f"Failed to save registry: {e}")
            raise
    
    def register_model(
        self,
        version: str,
        base_model: str,
        model_path: Path,
        metrics: Dict[str, Any],
        distilled_from: Optional[str] = None,
        quantization: Optional[str] = None,
        commit_hash: Optional[str] = None,
        set_active: bool = False,
    ) -> ModelRegistryEntry:
        """
        Register a new model in the registry.
        
        Args:
            version: Version identifier (e.g., "v3.1-week03")
            base_model: Base model name
            model_path: Path to model files
            metrics: Model performance metrics
            distilled_from: LoRA adapter ID if distilled
            quantization: Quantization level (e.g., "4bit")
            commit_hash: Git commit hash
            set_active: Whether to set as active model
        
        Returns:
            ModelRegistryEntry for the registered model
        """
        # Check for duplicate version
        existing = self.get_model(version)
        if existing:
            logger.warning(f"Model version {version} already exists, updating...")
            self.entries.remove(existing)
        
        entry = ModelRegistryEntry(
            version=version,
            base_model=base_model,
            distilled_from=distilled_from,
            quantization=quantization,
            model_path=str(model_path),
            timestamp=datetime.now(timezone.utc).isoformat(),
            metrics=metrics,
            active=set_active,
            last_good=False,
            commit_hash=commit_hash,
        )
        
        if set_active:
            # Mark current active as last_good before deactivating
            current_active = self.get_active()
            if current_active:
                current_active.last_good = True
            
            # Deactivate other models
            for e in self.entries:
                e.active = False
        
        self.entries.append(entry)
        self._save_registry()
        
        logger.info(f"Registered model: {version} (active={set_active})")
        
        return entry
    
    def get_latest(self, quantization: Optional[str] = None) -> Optional[ModelRegistryEntry]:
        """
        Get the most recent model entry.
        
        Args:
            quantization: Filter by quantization type
        
        Returns:
            Latest ModelRegistryEntry or None
        """
        if not self.entries:
            return None
        
        filtered = self.entries
        if quantization:
            filtered = [e for e in filtered if e.quantization == quantization]
        
        if not filtered:
            return None
        
        return max(filtered, key=lambda e: e.timestamp)
    
    def get_active(self) -> Optional[ModelRegistryEntry]:
        """
        Get the currently active model.
        
        Returns:
            Active ModelRegistryEntry or None
        """
        active_models = [e for e in self.entries if e.active]
        
        if not active_models:
            return None
        
        if len(active_models) > 1:
            logger.warning(f"Multiple active models found: {len(active_models)}")
        
        return active_models[0]
    
    def get_last_good(self) -> Optional[ModelRegistryEntry]:
        """
        Get the last known good model.
        
        Returns:
            Last good ModelRegistryEntry or None
        """
        good_models = [e for e in self.entries if e.last_good]
        
        if not good_models:
            return None
        
        return max(good_models, key=lambda e: e.timestamp)
    
    def get_model(self, version: str) -> Optional[ModelRegistryEntry]:
        """
        Get a specific model by version.
        
        Args:
            version: Version identifier
        
        Returns:
            ModelRegistryEntry or None
        """
        for entry in self.entries:
            if entry.version == version:
                return entry
        
        return None
    
    def list_models(
        self,
        base_model: Optional[str] = None,
        quantization: Optional[str] = None,
    ) -> List[ModelRegistryEntry]:
        """
        List models with optional filtering.
        
        Args:
            base_model: Filter by base model name
            quantization: Filter by quantization type
        
        Returns:
            List of ModelRegistryEntry objects
        """
        filtered = self.entries
        
        if base_model:
            filtered = [e for e in filtered if e.base_model == base_model]
        
        if quantization:
            filtered = [e for e in filtered if e.quantization == quantization]
        
        # Sort by timestamp (newest first)
        filtered.sort(key=lambda e: e.timestamp, reverse=True)
        
        return filtered
    
    def activate_model(self, version: str) -> bool:
        """
        Set a model as active.
        
        Args:
            version: Version to activate
        
        Returns:
            True if successful
        """
        model = self.get_model(version)
        if not model:
            logger.error(f"Model version not found: {version}")
            return False
        
        # Mark previous active as last_good if it was active
        current_active = self.get_active()
        if current_active:
            current_active.active = False
            current_active.last_good = True
        
        # Activate new model
        model.active = True
        
        self._save_registry()
        
        logger.info(f"Activated model: {version}")
        
        return True
    
    def rollback_model(self) -> Optional[ModelRegistryEntry]:
        """
        Rollback to the last known good model.
        
        Returns:
            The rolled-back ModelRegistryEntry or None
        """
        last_good = self.get_last_good()
        
        if not last_good:
            logger.error("No last good model found for rollback")
            return None
        
        # Deactivate current active
        current_active = self.get_active()
        if current_active:
            current_active.active = False
        
        # Activate last good
        last_good.active = True
        
        self._save_registry()
        
        logger.info(f"Rolled back to: {last_good.version}")
        
        return last_good
    
    def compare_models(
        self,
        version_a: str,
        version_b: str,
    ) -> Dict[str, Any]:
        """
        Compare two models.
        
        Args:
            version_a: First version
            version_b: Second version
        
        Returns:
            Comparison results dictionary
        """
        model_a = self.get_model(version_a)
        model_b = self.get_model(version_b)
        
        if not model_a or not model_b:
            logger.error("One or both models not found")
            return {}
        
        comparison = {
            "version_a": version_a,
            "version_b": version_b,
            "base_model_same": model_a.base_model == model_b.base_model,
            "metrics_delta": {},
        }
        
        # Compare metrics
        for key in set(model_a.metrics.keys()) | set(model_b.metrics.keys()):
            val_a = model_a.metrics.get(key)
            val_b = model_b.metrics.get(key)
            
            if val_a is not None and val_b is not None:
                if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                    comparison["metrics_delta"][key] = val_b - val_a
        
        logger.info(f"Compared models: {version_a} vs {version_b}")
        
        return comparison
    
    def export_registry(self, export_path: Path):
        """
        Export registry to a file.
        
        Args:
            export_path: Path to export to
        """
        shutil.copy2(self.registry_path, export_path)
        logger.info(f"Registry exported to: {export_path}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get registry statistics.
        
        Returns:
            Statistics dictionary
        """
        stats = {
            "total_models": len(self.entries),
            "active_model": None,
            "last_good_model": None,
            "quantization_breakdown": {},
            "base_model_breakdown": {},
        }
        
        active = self.get_active()
        if active:
            stats["active_model"] = active.version
        
        last_good = self.get_last_good()
        if last_good:
            stats["last_good_model"] = last_good.version
        
        # Count by quantization
        for entry in self.entries:
            quant = entry.quantization or "none"
            stats["quantization_breakdown"][quant] = stats["quantization_breakdown"].get(quant, 0) + 1
            
            base = entry.base_model
            stats["base_model_breakdown"][base] = stats["base_model_breakdown"].get(base, 0) + 1
        
        return stats
