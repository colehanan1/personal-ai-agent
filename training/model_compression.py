"""
Model Compression Module - REAL IMPLEMENTATION

Handles REAL quantization of models for edge deployment.
Supports GGUF via llama.cpp tooling.
NO PLACEHOLDERS. NO FAKE FILES.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from milton_orchestrator.state_paths import resolve_state_dir

logger = logging.getLogger(__name__)


@dataclass
class QuantizationConfig:
    """Configuration for model quantization."""
    bits: int = 4  # 4-bit or 8-bit quantization
    format: str = "gguf"  # gguf only for now
    quant_type: str = "Q4_0"  # Q4_0, Q4_1, Q8_0, etc.
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> QuantizationConfig:
        return cls(**data)


@dataclass
class CompressionMetrics:
    """REAL metrics from compression - NO FAKES."""
    original_size_mb: float
    compressed_size_mb: float
    compression_ratio: float
    quantization_bits: int
    quantization_type: str
    format: str
    validation_passed: bool
    has_gguf_file: bool
    gguf_file_path: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ModelCompression:
    """
    REAL model quantization using llama.cpp tooling.
    
    Requires:
    - llama.cpp installed with convert.py and llama-quantize
    - Set LLAMA_CPP_DIR environment variable
    
    Process:
    1. Convert HF model to GGUF format using convert.py
    2. Quantize using llama-quantize
    3. Validate output file exists and has reasonable size
    
    NO PLACEHOLDERS. Fails loudly if tools missing.
    """
    
    def __init__(
        self,
        quantized_dir: Optional[Path] = None,
        llama_cpp_dir: Optional[Path] = None,
    ):
        """
        Initialize model compression handler.
        
        Args:
            quantized_dir: Directory for quantized models
            llama_cpp_dir: Path to llama.cpp directory (overrides env var)
        """
        self.quantized_dir = quantized_dir or (resolve_state_dir() / "models" / "quantized")
        self.quantized_dir.mkdir(parents=True, exist_ok=True)
        
        # Get llama.cpp directory
        llama_cpp = llama_cpp_dir or os.getenv("LLAMA_CPP_DIR")
        self.llama_cpp_dir = Path(llama_cpp) if llama_cpp else None
        
        logger.info(f"ModelCompression initialized:")
        logger.info(f"  Output dir: {self.quantized_dir}")
        logger.info(f"  llama.cpp: {self.llama_cpp_dir or 'NOT SET'}")
    
    def _check_llama_cpp(self) -> bool:
        """Check if llama.cpp tools are available."""
        if not self.llama_cpp_dir:
            return False
        
        if not self.llama_cpp_dir.exists():
            return False
        
        # Check for required scripts
        convert_script = self.llama_cpp_dir / "convert_hf_to_gguf.py"
        quantize_bin = self.llama_cpp_dir / "llama-quantize"
        
        has_convert = convert_script.exists()
        has_quantize = quantize_bin.exists() and os.access(quantize_bin, os.X_OK)
        
        logger.info(f"  convert_hf_to_gguf.py: {'✓' if has_convert else '✗'}")
        logger.info(f"  llama-quantize: {'✓' if has_quantize else '✗'}")
        
        return has_convert and has_quantize
    
    def _estimate_model_size(self, model_path: Path) -> float:
        """Estimate model size in MB."""
        total_size = 0
        
        if model_path.is_file():
            total_size = model_path.stat().st_size
        elif model_path.is_dir():
            for item in model_path.rglob("*"):
                if item.is_file():
                    total_size += item.stat().st_size
        
        return total_size / (1024 * 1024)
    
    def quantize_model(
        self,
        model_path: Path,
        output_name: str,
        config: Optional[QuantizationConfig] = None,
        dry_run: bool = False,
    ) -> Tuple[Path, CompressionMetrics]:
        """
        REAL quantization using llama.cpp tooling.
        
        Args:
            model_path: Path to HF model directory
            output_name: Name for quantized output
            config: Quantization configuration
            dry_run: If True, verify setup but don't run
        
        Returns:
            Tuple of (output_path, real_metrics)
        
        Raises:
            FileNotFoundError: If model or tools missing
            RuntimeError: If quantization fails
        """
        if config is None:
            config = QuantizationConfig()
        
        # Map bits to quant type
        if config.bits == 4:
            config.quant_type = "Q4_0"
        elif config.bits == 8:
            config.quant_type = "Q8_0"
        
        logger.info("=" * 60)
        logger.info("REAL MODEL QUANTIZATION (llama.cpp)")
        logger.info("=" * 60)
        logger.info(f"Input model: {model_path}")
        logger.info(f"Output name: {output_name}")
        logger.info(f"Format: {config.format}")
        logger.info(f"Quantization: {config.quant_type} ({config.bits}-bit)")
        
        # Verify input model exists
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")
        
        original_size = self._estimate_model_size(model_path)
        logger.info(f"Original size: {original_size:.1f} MB")
        
        output_path = self.quantized_dir / output_name
        output_path.mkdir(parents=True, exist_ok=True)
        
        if dry_run:
            logger.info("DRY RUN: Would quantize but skipping actual compute")
            
            # Save config
            (output_path / "quantization_config.json").write_text(
                json.dumps(config.to_dict(), indent=2)
            )
            
            # NO FAKE METRICS in dry run
            metrics = CompressionMetrics(
                original_size_mb=original_size,
                compressed_size_mb=0.0,
                compression_ratio=0.0,
                quantization_bits=config.bits,
                quantization_type=config.quant_type,
                format=config.format,
                validation_passed=False,
                has_gguf_file=False,
                gguf_file_path=None,
            )
            return output_path, metrics
        
        # Check for llama.cpp
        if not self._check_llama_cpp():
            raise RuntimeError(
                "llama.cpp tools not found!\n"
                f"Set LLAMA_CPP_DIR environment variable or pass llama_cpp_dir parameter.\n"
                f"Current: {self.llama_cpp_dir}\n"
                "Clone llama.cpp and build:\n"
                "  git clone https://github.com/ggerganov/llama.cpp\n"
                "  cd llama.cpp && make\n"
                "  export LLAMA_CPP_DIR=$(pwd)"
            )
        
        if config.format != "gguf":
            raise ValueError(
                f"Only GGUF format is currently supported, got: {config.format}\n"
                "AWQ/GPTQ can be added later with AutoAWQ/AutoGPTQ libraries."
            )
        
        try:
            # Step 1: Convert HF to GGUF (fp16)
            logger.info("Step 1: Converting HF model to GGUF (fp16)...")
            
            temp_gguf = output_path / "model-fp16.gguf"
            convert_script = self.llama_cpp_dir / "convert_hf_to_gguf.py"
            
            convert_cmd = [
                "python",
                str(convert_script),
                str(model_path),
                "--outfile", str(temp_gguf),
                "--outtype", "f16",
            ]
            
            logger.info(f"Running: {' '.join(convert_cmd)}")
            result = subprocess.run(
                convert_cmd,
                capture_output=True,
                text=True,
                check=False,
            )
            
            if result.returncode != 0:
                logger.error(f"Convert stdout: {result.stdout}")
                logger.error(f"Convert stderr: {result.stderr}")
                raise RuntimeError(f"HF to GGUF conversion failed: {result.stderr}")
            
            if not temp_gguf.exists():
                raise RuntimeError(f"GGUF file not created: {temp_gguf}")
            
            fp16_size = temp_gguf.stat().st_size / (1024 * 1024)
            logger.info(f"✓ FP16 GGUF created: {fp16_size:.1f} MB")
            
            # Step 2: Quantize GGUF
            logger.info(f"Step 2: Quantizing to {config.quant_type}...")
            
            final_gguf = output_path / f"model-{config.quant_type.lower()}.gguf"
            quantize_bin = self.llama_cpp_dir / "llama-quantize"
            
            quant_cmd = [
                str(quantize_bin),
                str(temp_gguf),
                str(final_gguf),
                config.quant_type,
            ]
            
            logger.info(f"Running: {' '.join(quant_cmd)}")
            result = subprocess.run(
                quant_cmd,
                capture_output=True,
                text=True,
                check=False,
            )
            
            if result.returncode != 0:
                logger.error(f"Quantize stdout: {result.stdout}")
                logger.error(f"Quantize stderr: {result.stderr}")
                raise RuntimeError(f"Quantization failed: {result.stderr}")
            
            if not final_gguf.exists():
                raise RuntimeError(f"Quantized file not created: {final_gguf}")
            
            # Clean up temp file
            temp_gguf.unlink()
            
            compressed_size = final_gguf.stat().st_size / (1024 * 1024)
            logger.info(f"✓ Quantized GGUF created: {compressed_size:.1f} MB")
            
            # Validate size is reasonable (>50 MB for 8B model)
            if compressed_size < 50:
                logger.warning(f"GGUF file suspiciously small: {compressed_size:.1f} MB")
            
            # Save config
            (output_path / "quantization_config.json").write_text(
                json.dumps(config.to_dict(), indent=2)
            )
            
            # Create REAL metrics
            compression_ratio = original_size / compressed_size if compressed_size > 0 else 0
            
            metrics = CompressionMetrics(
                original_size_mb=original_size,
                compressed_size_mb=compressed_size,
                compression_ratio=compression_ratio,
                quantization_bits=config.bits,
                quantization_type=config.quant_type,
                format=config.format,
                validation_passed=compressed_size >= 50,
                has_gguf_file=True,
                gguf_file_path=str(final_gguf),
            )
            
            # Save metrics
            (output_path / "metrics.json").write_text(
                json.dumps(metrics.to_dict(), indent=2)
            )
            
            logger.info("=" * 60)
            logger.info("QUANTIZATION COMPLETE")
            logger.info(f"Original: {metrics.original_size_mb:.1f} MB")
            logger.info(f"Compressed: {metrics.compressed_size_mb:.1f} MB")
            logger.info(f"Ratio: {metrics.compression_ratio:.2f}x")
            logger.info(f"File: {final_gguf}")
            logger.info("=" * 60)
            
            return output_path, metrics
            
        except Exception as e:
            logger.error(f"Quantization failed: {e}", exc_info=True)
            raise RuntimeError(f"Model quantization failed: {e}") from e
    
    def validate_quantized_model(
        self,
        quantized_model_path: Path,
    ) -> Dict[str, Any]:
        """
        Validate quantized model.
        
        Args:
            quantized_model_path: Path to quantized model directory
        
        Returns:
            Validation results dictionary
        """
        logger.info(f"Validating quantized model: {quantized_model_path}")
        
        # Check for GGUF file
        gguf_files = list(quantized_model_path.glob("*.gguf"))
        
        validation = {
            "has_gguf_files": len(gguf_files) > 0,
            "gguf_count": len(gguf_files),
            "gguf_files": [str(f.name) for f in gguf_files],
            "validation_passed": False,
        }
        
        if gguf_files:
            # Check size
            total_size = sum(f.stat().st_size for f in gguf_files) / (1024 * 1024)
            validation["total_size_mb"] = total_size
            validation["validation_passed"] = total_size >= 50
            
            logger.info(f"Found {len(gguf_files)} GGUF file(s), total size: {total_size:.1f} MB")
        else:
            logger.warning("No GGUF files found!")
            validation["total_size_mb"] = 0.0
        
        return validation
    
    def get_quantized_model_info(self, model_path: Path) -> Dict[str, Any]:
        """
        Get information about a quantized model.
        
        Args:
            model_path: Path to quantized model
        
        Returns:
            Dictionary with model metadata
        """
        config_path = model_path / "quantization_config.json"
        metrics_path = model_path / "metrics.json"
        
        info = {
            "path": str(model_path),
            "exists": model_path.exists(),
            "size_mb": self._estimate_model_size(model_path),
        }
        
        if config_path.exists():
            info["config"] = json.loads(config_path.read_text())
        
        if metrics_path.exists():
            info["metrics"] = json.loads(metrics_path.read_text())
        
        # Find GGUF files
        gguf_files = []
        if model_path.is_dir():
            gguf_files = [str(f.name) for f in model_path.glob("*.gguf")]
        
        info["gguf_files"] = gguf_files
        info["has_gguf"] = len(gguf_files) > 0
        
        return info
