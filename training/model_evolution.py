"""
Model Evolution Module - REAL IMPLEMENTATION

Handles REAL distillation of LoRA adapters into optimized models.
No placeholders, no fake metrics, no stubs.

Strategy: PEFT merge_and_unload to create standalone models.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from milton_orchestrator.state_paths import resolve_state_dir

logger = logging.getLogger(__name__)

# Base model path - MANDATORY
BASE_MODEL_PATH = Path.home() / "milton" / "models" / "Llama-3.1-8B-Instruct-HF"


@dataclass
class DistillationConfig:
    """Configuration for model distillation."""
    teacher_model_path: str
    adapter_path: Optional[str] = None
    prune_magnitude_threshold: float = 0.0  # Disabled by default
    copy_base_model: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DistillationConfig:
        return cls(**data)


@dataclass
class DistillationMetrics:
    """REAL metrics from distillation process - NO FAKES."""
    method: str  # "peft_merge" or "copy_only"
    model_size_mb: float
    parameter_count: int
    has_adapter: bool
    adapter_merged: bool
    training_time_seconds: float
    base_model_path: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ModelEvolution:
    """
    REAL model evolution through PEFT adapter merging.
    
    Strategy:
    1. Verify base model exists at canonical path
    2. Load base model + LoRA adapter using PEFT
    3. Merge adapter weights into base using merge_and_unload()
    4. Save merged model as standalone HF model
    5. Compute REAL metrics (size, param count)
    
    NO PLACEHOLDERS. NO FAKE METRICS.
    """
    
    def __init__(
        self,
        models_dir: Optional[Path] = None,
        adapters_dir: Optional[Path] = None,
        base_model_path: Optional[Path] = None,
    ):
        """
        Initialize model evolution orchestrator.
        
        Args:
            models_dir: Directory for distilled models
            adapters_dir: Directory containing LoRA adapters
            base_model_path: Path to base model (overrides default)
        """
        self.models_dir = models_dir or (resolve_state_dir() / "models" / "distilled")
        self.adapters_dir = adapters_dir or (resolve_state_dir() / "adapters")
        self.base_model_path = base_model_path or BASE_MODEL_PATH
        
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # Verify base model exists
        if not self.base_model_path.exists():
            raise FileNotFoundError(
                f"Base model not found at: {self.base_model_path}\n"
                f"Cannot proceed with distillation."
            )
        
        logger.info(f"ModelEvolution initialized:")
        logger.info(f"  Base model: {self.base_model_path}")
        logger.info(f"  Output dir: {self.models_dir}")
    
    def _verify_dependencies(self) -> None:
        """Verify required packages are installed."""
        try:
            import torch
            import transformers
            from peft import PeftModel
        except ImportError as e:
            raise RuntimeError(
                f"Missing required package: {e}\n"
                f"Install with: pip install torch transformers peft"
            ) from e
    
    def _count_parameters(self, model) -> int:
        """Count total parameters in model."""
        try:
            return sum(p.numel() for p in model.parameters())
        except Exception as e:
            logger.warning(f"Could not count parameters: {e}")
            return 0
    
    def _get_model_size_mb(self, model_path: Path) -> float:
        """Calculate total size of model files in MB."""
        total_size = 0
        if model_path.is_dir():
            for item in model_path.rglob("*"):
                if item.is_file():
                    total_size += item.stat().st_size
        return total_size / (1024 * 1024)
    
    def distill_model(
        self,
        base_model_path: str,
        adapter_path: Optional[str],
        output_path: Path,
        config: Optional[DistillationConfig] = None,
        dry_run: bool = False,
    ) -> Tuple[Path, DistillationMetrics]:
        """
        REAL distillation: merge LoRA adapter into base model.
        
        If adapter_path is None, just copies the base model.
        If adapter_path is provided, loads and merges using PEFT.
        
        Args:
            base_model_path: Path to base model (usually BASE_MODEL_PATH)
            adapter_path: Path to LoRA adapter (optional)
            output_path: Where to save merged model
            config: Distillation configuration
            dry_run: If True, verify setup but don't run
        
        Returns:
            Tuple of (output_path, real_metrics)
        
        Raises:
            FileNotFoundError: If base model or adapter missing
            RuntimeError: If dependencies missing
        """
        if config is None:
            config = DistillationConfig(teacher_model_path=base_model_path)
        
        start_time = time.time()
        
        logger.info("=" * 60)
        logger.info("REAL MODEL DISTILLATION (PEFT merge)")
        logger.info("=" * 60)
        logger.info(f"Base model: {base_model_path}")
        logger.info(f"Adapter: {adapter_path or 'None (base only)'}")
        logger.info(f"Output: {output_path}")
        
        # Verify base model exists
        base_path = Path(base_model_path)
        if not base_path.exists():
            raise FileNotFoundError(f"Base model not found: {base_path}")
        
        # Verify adapter exists if provided
        has_adapter = False
        if adapter_path:
            adapter_p = Path(adapter_path)
            if not adapter_p.exists():
                raise FileNotFoundError(f"Adapter not found: {adapter_p}")
            has_adapter = True
        
        if dry_run:
            logger.info("DRY RUN: Would merge model but skipping actual compute")
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Create config file to show intent
            (output_path / "distillation_config.json").write_text(
                json.dumps(config.to_dict(), indent=2)
            )
            
            # NO FAKE METRICS in dry run - return minimal real data
            metrics = DistillationMetrics(
                method="dry_run",
                model_size_mb=0.0,
                parameter_count=0,
                has_adapter=has_adapter,
                adapter_merged=False,
                training_time_seconds=time.time() - start_time,
                base_model_path=str(base_path),
            )
            return output_path, metrics
        
        # REAL IMPLEMENTATION
        self._verify_dependencies()
        
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import PeftModel
            
            logger.info("Loading base model...")
            model = AutoModelForCausalLM.from_pretrained(
                base_model_path,
                torch_dtype=torch.float16,
                device_map="auto",
                low_cpu_mem_usage=True,
            )
            
            tokenizer = AutoTokenizer.from_pretrained(base_model_path)
            
            merged_model = model
            adapter_merged = False
            
            if adapter_path:
                logger.info(f"Loading LoRA adapter from: {adapter_path}")
                model = PeftModel.from_pretrained(model, adapter_path)
                
                logger.info("Merging adapter weights into base model...")
                merged_model = model.merge_and_unload()
                adapter_merged = True
                logger.info("✓ Adapter merged successfully")
            else:
                logger.info("No adapter provided, using base model as-is")
            
            # Count parameters
            param_count = self._count_parameters(merged_model)
            logger.info(f"Model has {param_count:,} parameters")
            
            # Save merged model
            logger.info(f"Saving merged model to: {output_path}")
            output_path.mkdir(parents=True, exist_ok=True)
            
            merged_model.save_pretrained(output_path)
            tokenizer.save_pretrained(output_path)
            
            logger.info("✓ Model saved successfully")
            
            # Calculate real size
            model_size_mb = self._get_model_size_mb(output_path)
            logger.info(f"Output size: {model_size_mb:.1f} MB")
            
            # Save config
            (output_path / "distillation_config.json").write_text(
                json.dumps(config.to_dict(), indent=2)
            )
            
            elapsed = time.time() - start_time
            
            # Create REAL metrics
            metrics = DistillationMetrics(
                method="peft_merge" if adapter_merged else "copy_base",
                model_size_mb=model_size_mb,
                parameter_count=param_count,
                has_adapter=has_adapter,
                adapter_merged=adapter_merged,
                training_time_seconds=elapsed,
                base_model_path=str(base_path),
            )
            
            # Save metrics
            (output_path / "metrics.json").write_text(
                json.dumps(metrics.to_dict(), indent=2)
            )
            
            logger.info("=" * 60)
            logger.info("DISTILLATION COMPLETE")
            logger.info(f"Method: {metrics.method}")
            logger.info(f"Parameters: {metrics.parameter_count:,}")
            logger.info(f"Size: {metrics.model_size_mb:.1f} MB")
            logger.info(f"Time: {metrics.training_time_seconds:.1f}s")
            logger.info("=" * 60)
            
            return output_path, metrics
            
        except Exception as e:
            logger.error(f"Distillation failed: {e}", exc_info=True)
            raise RuntimeError(f"Model distillation failed: {e}") from e
    
    
    def get_model_info(self, model_path: Path) -> Dict[str, Any]:
        """
        Get REAL information about a distilled model.
        
        Args:
            model_path: Path to model
        
        Returns:
            Dictionary with model metadata
        """
        config_path = model_path / "distillation_config.json"
        metrics_path = model_path / "metrics.json"
        
        info = {
            "path": str(model_path),
            "exists": model_path.exists(),
        }
        
        if config_path.exists():
            info["config"] = json.loads(config_path.read_text())
        
        if metrics_path.exists():
            info["metrics"] = json.loads(metrics_path.read_text())
        
        # Check for actual model files
        has_model = False
        model_files = []
        if model_path.is_dir():
            for ext in [".safetensors", ".bin", ".pt"]:
                files = list(model_path.glob(f"*{ext}"))
                if files:
                    has_model = True
                    model_files.extend([str(f.name) for f in files])
        
        info["has_model_files"] = has_model
        info["model_files"] = model_files
        info["size_mb"] = self._get_model_size_mb(model_path) if model_path.exists() else 0.0
        
        return info
