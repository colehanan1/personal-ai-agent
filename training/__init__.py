"""
Training Module for Milton LoRA Fine-Tuning

Provides continuous LoRA training pipeline with:
- Data pipeline (conversation logs → training data)
- LoRA training orchestration
- Evaluation metrics (PPL, semantic, CoVe)
- Adapter lifecycle management
"""
from .data_pipeline import DataPipeline, TrainingExample
from .eval_metrics import EvalMetrics, EvaluationResult
from .adapter_manager import AdapterManager, AdapterInfo
from .continuous_trainer import ContinuousTrainer, TrainingConfig, train_lora_adapter

__all__ = [
    "DataPipeline",
    "TrainingExample",
    "EvalMetrics",
    "EvaluationResult",
    "AdapterManager",
    "AdapterInfo",
    "ContinuousTrainer",
    "TrainingConfig",
    "train_lora_adapter",
]
