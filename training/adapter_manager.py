"""
LoRA Adapter Manager

Manages loading, activation, deactivation, and rollback of LoRA adapters.
Maintains adapter registry with version tracking and quality metrics.
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
class AdapterInfo:
    """Information about a registered adapter."""
    name: str
    version: str
    timestamp: str
    adapter_path: str
    quality_score: float
    metrics: Dict[str, Any]
    active: bool
    last_good: bool  # Is this the last known good adapter?

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AdapterInfo:
        """Create from dictionary."""
        return cls(**data)


class AdapterManager:
    """
    Manages LoRA adapter lifecycle.
    
    Handles:
    - Adapter registration and tracking
    - Activation/deactivation
    - Rollback to previous versions
    - Quality-based promotion/demotion
    
    Attributes:
        adapters_dir: Directory containing adapter checkpoints
        registry_path: Path to adapter registry JSON
    """
    
    def __init__(
        self,
        adapters_dir: Optional[Path] = None,
        registry_path: Optional[Path] = None,
    ):
        """
        Initialize AdapterManager.
        
        Args:
            adapters_dir: Directory for adapter storage
            registry_path: Path to registry file
        """
        state_dir = resolve_state_dir()
        
        if adapters_dir is None:
            adapters_dir = state_dir / "adapters"
        self.adapters_dir = Path(adapters_dir)
        self.adapters_dir.mkdir(parents=True, exist_ok=True)
        
        if registry_path is None:
            registry_path = self.adapters_dir / "adapter_registry.json"
        self.registry_path = Path(registry_path)
        
        self._registry: Dict[str, AdapterInfo] = {}
        self._load_registry()
        
        logger.info(f"AdapterManager initialized: {self.adapters_dir}")
    
    def _load_registry(self) -> None:
        """Load adapter registry from disk."""
        if not self.registry_path.exists():
            logger.info("Creating new adapter registry")
            self._save_registry()
            return
        
        try:
            with open(self.registry_path, 'r') as f:
                data = json.load(f)
            
            self._registry = {
                name: AdapterInfo.from_dict(info)
                for name, info in data.items()
            }
            
            logger.info(f"Loaded {len(self._registry)} adapters from registry")
            
        except Exception as e:
            logger.error(f"Failed to load registry: {e}")
            self._registry = {}
    
    def _save_registry(self) -> None:
        """Save adapter registry to disk."""
        try:
            data = {
                name: info.to_dict()
                for name, info in self._registry.items()
            }
            
            with open(self.registry_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug("Adapter registry saved")
            
        except Exception as e:
            logger.error(f"Failed to save registry: {e}")
    
    def register_adapter(
        self,
        name: str,
        adapter_path: Path,
        quality_score: float,
        metrics: Optional[Dict[str, Any]] = None,
        auto_activate: bool = False,
    ) -> AdapterInfo:
        """
        Register a new adapter in the registry.
        
        Args:
            name: Adapter name (e.g., "week_02_lora")
            adapter_path: Path to adapter checkpoint
            quality_score: Overall quality score
            metrics: Evaluation metrics
            auto_activate: Automatically activate if quality is good
            
        Returns:
            AdapterInfo object
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        version = timestamp.split('T')[0].replace('-', '')
        
        adapter_info = AdapterInfo(
            name=name,
            version=version,
            timestamp=timestamp,
            adapter_path=str(adapter_path),
            quality_score=quality_score,
            metrics=metrics or {},
            active=False,
            last_good=False,
        )
        
        self._registry[name] = adapter_info
        self._save_registry()
        
        logger.info(
            f"Registered adapter: {name} (quality={quality_score:.2%})"
        )
        
        # Auto-activate if quality is good
        if auto_activate and quality_score >= 0.7:
            self.activate(name)
        
        return adapter_info
    
    def activate(self, name: str) -> bool:
        """
        Activate an adapter.
        
        Deactivates all other adapters and marks this one as active.
        
        Args:
            name: Adapter name to activate
            
        Returns:
            True if successful, False otherwise
        """
        if name not in self._registry:
            logger.error(f"Adapter not found: {name}")
            return False
        
        # Deactivate all adapters
        for adapter_name in self._registry:
            self._registry[adapter_name].active = False
        
        # Activate target adapter
        self._registry[name].active = True
        
        # Mark as last good if quality is acceptable
        adapter = self._registry[name]
        if adapter.quality_score >= 0.7:
            # Clear old last_good flags
            for adapter_name in self._registry:
                self._registry[adapter_name].last_good = False
            adapter.last_good = True
        
        self._save_registry()
        
        logger.info(f"Activated adapter: {name}")
        return True
    
    def deactivate(self, name: str) -> bool:
        """
        Deactivate an adapter.
        
        Args:
            name: Adapter name to deactivate
            
        Returns:
            True if successful, False otherwise
        """
        if name not in self._registry:
            logger.error(f"Adapter not found: {name}")
            return False
        
        self._registry[name].active = False
        self._save_registry()
        
        logger.info(f"Deactivated adapter: {name}")
        return True
    
    def rollback(self, target_name: Optional[str] = None) -> Optional[str]:
        """
        Rollback to a previous adapter.
        
        If target_name is provided, rolls back to that adapter.
        Otherwise, rolls back to the last known good adapter.
        
        Args:
            target_name: Target adapter name (optional)
            
        Returns:
            Name of activated adapter, or None if rollback failed
        """
        if target_name:
            # Rollback to specific adapter
            if target_name not in self._registry:
                logger.error(f"Target adapter not found: {target_name}")
                return None
            
            if self.activate(target_name):
                logger.info(f"Rolled back to adapter: {target_name}")
                return target_name
            return None
        
        # Find last known good adapter
        last_good = None
        for adapter_name, info in self._registry.items():
            if info.last_good:
                last_good = adapter_name
                break
        
        if not last_good:
            logger.warning("No last known good adapter found")
            return None
        
        if self.activate(last_good):
            logger.info(f"Rolled back to last good adapter: {last_good}")
            return last_good
        
        return None
    
    def list_adapters(
        self,
        active_only: bool = False,
    ) -> List[AdapterInfo]:
        """
        List registered adapters.
        
        Args:
            active_only: Only return active adapters
            
        Returns:
            List of AdapterInfo objects
        """
        adapters = list(self._registry.values())
        
        if active_only:
            adapters = [a for a in adapters if a.active]
        
        # Sort by timestamp (newest first)
        adapters.sort(key=lambda a: a.timestamp, reverse=True)
        
        return adapters
    
    def current_adapter(self) -> Optional[AdapterInfo]:
        """
        Get currently active adapter.
        
        Returns:
            AdapterInfo of active adapter, or None if no adapter is active
        """
        for adapter in self._registry.values():
            if adapter.active:
                return adapter
        return None
    
    def get_adapter(self, name: str) -> Optional[AdapterInfo]:
        """
        Get adapter info by name.
        
        Args:
            name: Adapter name
            
        Returns:
            AdapterInfo or None if not found
        """
        return self._registry.get(name)
    
    def delete_adapter(self, name: str, delete_files: bool = False) -> bool:
        """
        Delete an adapter from registry.
        
        Args:
            name: Adapter name
            delete_files: Also delete adapter files from disk
            
        Returns:
            True if successful
        """
        if name not in self._registry:
            logger.error(f"Adapter not found: {name}")
            return False
        
        adapter = self._registry[name]
        
        # Delete files if requested
        if delete_files:
            adapter_path = Path(adapter.adapter_path)
            if adapter_path.exists():
                try:
                    if adapter_path.is_dir():
                        shutil.rmtree(adapter_path)
                    else:
                        adapter_path.unlink()
                    logger.info(f"Deleted adapter files: {adapter_path}")
                except Exception as e:
                    logger.error(f"Failed to delete adapter files: {e}")
        
        # Remove from registry
        del self._registry[name]
        self._save_registry()
        
        logger.info(f"Deleted adapter from registry: {name}")
        return True


if __name__ == "__main__":
    # Test adapter manager
    logging.basicConfig(level=logging.INFO)
    
    print("Testing AdapterManager...")
    
    # Create temp manager
    import tempfile
    temp_dir = Path(tempfile.mkdtemp())
    
    manager = AdapterManager(
        adapters_dir=temp_dir / "adapters",
        registry_path=temp_dir / "registry.json",
    )
    
    print("\nRegistering adapters...")
    adapter1 = manager.register_adapter(
        name="week_01_lora",
        adapter_path=temp_dir / "adapters" / "week_01",
        quality_score=0.85,
        metrics={"ppl_change": -3.2, "cove_pass_rate": 0.92},
    )
    print(f"  Registered: {adapter1.name} (quality={adapter1.quality_score:.2%})")
    
    adapter2 = manager.register_adapter(
        name="week_02_lora",
        adapter_path=temp_dir / "adapters" / "week_02",
        quality_score=0.78,
        metrics={"ppl_change": -2.1, "cove_pass_rate": 0.90},
    )
    print(f"  Registered: {adapter2.name} (quality={adapter2.quality_score:.2%})")
    
    print("\nActivating adapter...")
    manager.activate("week_02_lora")
    current = manager.current_adapter()
    print(f"  Active: {current.name if current else 'None'}")
    
    print("\nTesting rollback...")
    manager.rollback()
    current = manager.current_adapter()
    print(f"  After rollback: {current.name if current else 'None'}")
    
    print("\nListing adapters:")
    for adapter in manager.list_adapters():
        status = "ACTIVE" if adapter.active else "inactive"
        last_good = " [LAST GOOD]" if adapter.last_good else ""
        print(f"  {adapter.name}: {status} (quality={adapter.quality_score:.2%}){last_good}")
    
    # Cleanup
    shutil.rmtree(temp_dir)
    
    print("\n✅ AdapterManager test complete")
