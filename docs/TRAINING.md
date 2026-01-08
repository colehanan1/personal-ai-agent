# Milton LoRA Fine-Tuning Pipeline

Complete guide to training personalized LoRA adapters on your conversation data.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Workflow](#workflow)
- [Configuration Guide](#configuration-guide)
- [GPU Requirements](#gpu-requirements)
- [Evaluation Metrics](#evaluation-metrics)
- [Promotion Workflow](#promotion-workflow)
- [Rollback Procedure](#rollback-procedure)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Example Commands](#example-commands)

---

## Overview

The LoRA fine-tuning pipeline allows you to continuously adapt Milton to your personal communication style and preferences by training on your conversation history.

### What is LoRA?

LoRA (Low-Rank Adaptation) is an efficient fine-tuning technique that:
- Trains only ~1% of model parameters
- Produces small adapter files (~80-640MB depending on rank)
- Preserves base model knowledge while adapting to your data
- Can be swapped, versioned, and rolled back easily

### Pipeline Components

```
┌─────────────────────┐
│ 1. Export Data      │  Memory → JSONL (with PII filtering)
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ 2. Train Adapter    │  JSONL → LoRA adapter
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ 3. Evaluate         │  Compute metrics, auto-promote to "candidate"
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ 4. Promote          │  Manual promotion to "production"
└─────────────────────┘
```

---

## Prerequisites

### Hardware

- **GPU**: NVIDIA GPU with ≥16GB VRAM (RTX 5090 with 32GB recommended)
- **RAM**: ≥32GB system RAM
- **Disk**: ≥20GB free space

### Software

```bash
# Python dependencies
pip install transformers peft datasets accelerate bitsandbytes

# Verify installation
python -c "import torch; print(torch.cuda.is_available())"
```

### Base Model

Ensure you have the base model downloaded:

```bash
ls ~/milton/models/Llama-3.1-8B-Instruct-HF
```

---

## Quick Start

### Complete Workflow (Weekly Retraining)

```bash
# 1. Export last 30 days of conversations
python scripts/export_training_data.py --days 30

# 2. Train LoRA adapter (~10 minutes)
python scripts/train_lora.py --config training/configs/lora_default.yaml

# 3. Evaluate adapter (auto-promotes to candidate if ≥90% pass)
python scripts/eval_lora.py --run-id lora_YYYYMMDD_HHMMSS

# 4. Review metrics and promote to production
cat runs/lora_YYYYMMDD_HHMMSS/metrics.json
python scripts/promote_adapter.py lora_YYYYMMDD_HHMMSS --to-production

# 5. Restart vLLM with new adapter (future: automatic adapter loading)
scripts/stop_all.sh && scripts/start_all.sh
```

---

## Workflow

### Step 1: Export Training Data

Export conversations from Milton's memory to JSONL format:

```bash
# Export last 30 days
python scripts/export_training_data.py --days 30

# Preview without writing files
python scripts/export_training_data.py --days 30 --dry-run

# Custom output directory
python scripts/export_training_data.py --days 30 --output-dir /custom/path
```

**Output**:
- `training/data/exported/train.jsonl` - Training examples (80%)
- `training/data/exported/test.jsonl` - Test examples (20%)
- `training/data/exported/metadata.json` - Dataset provenance

**PII Filtering**: Automatically redacts:
- Email addresses → `[EMAIL]`
- Phone numbers → `[PHONE]`
- API keys → `[API_KEY]`
- URLs with tokens → `[URL_WITH_TOKEN]`

### Step 2: Train LoRA Adapter

Train a LoRA adapter on exported data:

```bash
# Default config (r=16, balanced)
python scripts/train_lora.py --config training/configs/lora_default.yaml

# Light config (r=8, faster)
python scripts/train_lora.py --config training/configs/lora_light.yaml

# Heavy config (r=64, comprehensive)
python scripts/train_lora.py --config training/configs/lora_heavy.yaml

# Dry run to validate config
python scripts/train_lora.py --config lora_default.yaml --dry-run
```

**Output**:
- `adapters/lora_YYYYMMDD_HHMMSS/` - Trained adapter weights
  - `adapter_config.json` - LoRA configuration
  - `adapter_model.safetensors` - Adapter weights
  - `metadata.json` - Training provenance
- `runs/lora_YYYYMMDD_HHMMSS/` - Training artifacts
  - `logs/` - TensorBoard logs
  - `checkpoints/` - Epoch checkpoints

**Safety Checks**:
- ✅ Base model exists
- ✅ Training data exists (≥10 examples)
- ✅ Disk space available (≥10GB)
- ⚠️ Git repository clean (warning only)

### Step 3: Evaluate Adapter

Compute metrics and benchmarks:

```bash
# Evaluate adapter
python scripts/eval_lora.py --run-id lora_YYYYMMDD_HHMMSS

# Skip auto-promotion
python scripts/eval_lora.py --run-id lora_YYYYMMDD_HHMMSS --no-auto-promote

# Dry run
python scripts/eval_lora.py --run-id lora_YYYYMMDD_HHMMSS --dry-run
```

**Output**:
- `runs/lora_YYYYMMDD_HHMMSS/metrics.json` - Evaluation results
- `runs/lora_YYYYMMDD_HHMMSS/sanity_responses.json` - Qualitative responses

**Auto-Promotion**: If overall benchmark pass rate ≥90%, status automatically updates from `training` → `candidate`

### Step 4: Promote to Production

Manual promotion to production status:

```bash
# List all adapters
python scripts/promote_adapter.py --list

# Promote to production (requires confirmation)
python scripts/promote_adapter.py lora_YYYYMMDD_HHMMSS --to-production

# Force promotion (skip confirmation)
python scripts/promote_adapter.py lora_YYYYMMDD_HHMMSS --to-production --force

# Archive adapter
python scripts/promote_adapter.py lora_YYYYMMDD_HHMMSS --archive
```

**Confirmation Prompt**:
```
⚠️  Promotion to PRODUCTION
   New adapter: lora_20260105_142301
   Status: candidate → production
   Current production: lora_20260101_120000 (will be archived)

   Evaluation metrics:
     perplexity: 1.87
     eval_loss: 0.241
     token_accuracy: 0.876
     Task pass rate: 94.4%

   Proceed? [y/N]:
```

---

## Configuration Guide

### Available Configs

| Config | Rank | Size | Time | Use Case |
|--------|------|------|------|----------|
| `lora_light.yaml` | r=8 | ~80MB | ~5min | Daily updates |
| `lora_default.yaml` | r=16 | ~160MB | ~10min | Weekly retraining |
| `lora_heavy.yaml` | r=64 | ~640MB | ~30min | Monthly comprehensive |

### YAML Parameters

```yaml
# Model paths
base_model_path: /path/to/base/model
run_name_prefix: lora  # Prefix for run IDs

# LoRA hyperparameters
lora_r: 16             # Rank (higher = more capacity, slower)
lora_alpha: 32         # Scaling factor (usually 2 * r)
lora_dropout: 0.1      # Dropout rate
target_modules:        # Which layers to adapt
  - q_proj
  - k_proj
  - v_proj
  - o_proj
  - gate_proj
  - up_proj
  - down_proj

# Training hyperparameters
learning_rate: 3.0e-4
num_epochs: 3
per_device_train_batch_size: 4
gradient_accumulation_steps: 4
bf16: true
lr_scheduler_type: cosine
warmup_steps: 10
max_grad_norm: 1.0

# Data paths
train_file: training/data/exported/train.jsonl
test_file: training/data/exported/test.jsonl

# Output paths
adapters_dir: adapters
runs_dir: runs

# Advanced options
max_seq_length: 2048
use_gradient_checkpointing: true
```

### Custom Configuration

Create your own config:

```yaml
# training/configs/lora_custom.yaml
base_model_path: /home/cole-hanan/milton/models/Llama-3.1-8B-Instruct-HF
run_name_prefix: lora_custom
lora_r: 24
lora_alpha: 48
num_epochs: 4
learning_rate: 2.5e-4
# ... (other params)
```

---

## GPU Requirements

### VRAM Usage by Config

| Config | Batch Size | VRAM Usage | RTX 5090 (32GB) |
|--------|-----------|------------|-----------------|
| Light (r=8) | 8 | ~12GB | ✅ Plenty of headroom |
| Default (r=16) | 4 | ~18GB | ✅ Comfortable |
| Heavy (r=64) | 2 | ~28GB | ✅ Close to limit |

### OOM Troubleshooting

If you get out-of-memory errors:

1. **Reduce batch size**:
   ```yaml
   per_device_train_batch_size: 2
   gradient_accumulation_steps: 8  # Increase to compensate
   ```

2. **Use smaller rank**:
   ```yaml
   lora_r: 8
   lora_alpha: 16
   ```

3. **Reduce sequence length**:
   ```yaml
   max_seq_length: 1024
   ```

---

## Evaluation Metrics

### Test Set Metrics

Computed on held-out test data:

- **Perplexity**: How "surprised" the model is by test data (lower = better)
  - Good: < 2.0
  - Acceptable: 2.0 - 3.0
  - Poor: > 3.0

- **Eval Loss**: Cross-entropy loss (lower = better)
  - Good: < 0.5
  - Acceptable: 0.5 - 1.0
  - Poor: > 1.0

- **Token Accuracy**: % of correctly predicted tokens
  - Good: > 85%
  - Acceptable: 75% - 85%
  - Poor: < 75%

### Sanity Prompts

10 handcrafted prompts covering:
- Self-awareness ("What are you?")
- Task management (reminders, briefings)
- Context recall (memory retrieval)
- Code generation
- Safety alignment (refusal of harmful requests)

Responses saved to `runs/<run_id>/sanity_responses.json` for manual review.

### Task Benchmarks

Milton-specific tests with pass/fail criteria:

- **Memory retrieval** (5 tests)
- **Briefing generation** (3 tests)
- **Code execution** (4 tests)
- **Safety alignment** (5 tests)
- **Task understanding** (3 tests)

**Overall pass rate** ≥90% triggers auto-promotion to candidate.

---

## Promotion Workflow

### Status Lifecycle

```
training → candidate → production
             ↓
          archived
```

### Status Definitions

| Status | Meaning | Auto/Manual |
|--------|---------|-------------|
| `training` | Just trained, not evaluated | Auto |
| `candidate` | Evaluated, passed benchmarks | Auto (≥90% pass) |
| `production` | Currently deployed | Manual only |
| `archived` | Previously production, replaced | Auto on promotion |

### Safe Promotion

```bash
# 1. Check current production
python scripts/promote_adapter.py --list

# 2. Review candidate metrics
cat runs/lora_NEW/metrics.json

# 3. Promote (requires confirmation)
python scripts/promote_adapter.py lora_NEW --to-production
```

### What Happens on Promotion

1. Current production adapter → `archived` status
2. New adapter → `production` status
3. Registry updated with timestamps
4. Previous production preserved (for rollback)

**Note**: vLLM restart required to load new adapter (future: hot-swapping)

---

## Rollback Procedure

If new adapter causes issues:

```bash
# 1. Check what will be restored
python scripts/promote_adapter.py --list

# 2. Rollback to previous production
python scripts/promote_adapter.py --rollback

# 3. Restart vLLM
scripts/stop_all.sh && scripts/start_all.sh
```

Rollback automatically:
- Finds most recent `archived` adapter
- Promotes it back to `production`
- Archives current production

---

## Monitoring

### TensorBoard

Monitor training in real-time:

```bash
# Start TensorBoard
tensorboard --logdir runs/

# Open browser to http://localhost:6006

# View specific run
tensorboard --logdir runs/lora_20260105_142301/logs
```

**Metrics to Watch**:
- `train/loss` - Should decrease over epochs
- `eval/loss` - Should decrease without diverging from train
- `train/learning_rate` - Cosine decay schedule

### Registry Status

```bash
# List all adapters with status
python scripts/promote_adapter.py --list

# Example output:
# Run ID                    Status        Created      Pass Rate
# -----------------------------------------------------------------
# lora_20260101_120000      archived      2026-01-01   92.5%
# lora_20260105_140000      production ★  2026-01-05   94.4%
# lora_20260106_090000      candidate     2026-01-06   91.2%
```

### Adapter Metadata

```bash
# View full adapter metadata
cat adapters/lora_20260105_142301/metadata.json

# View evaluation metrics
cat runs/lora_20260105_142301/metrics.json
```

---

## Troubleshooting

### Training Fails with OOM

**Symptom**: `CUDA out of memory` error

**Solution**:
```yaml
# Reduce batch size and increase accumulation
per_device_train_batch_size: 2
gradient_accumulation_steps: 8
```

### Poor Evaluation Metrics

**Symptom**: Perplexity > 3.0, token accuracy < 75%

**Possible Causes**:
1. **Too few training examples**: Export more days
   ```bash
   python scripts/export_training_data.py --days 60
   ```

2. **Learning rate too high**: Reduce in config
   ```yaml
   learning_rate: 1.0e-4
   ```

3. **Too few epochs**: Increase training
   ```yaml
   num_epochs: 5
   ```

### Training Stuck at High Loss

**Symptom**: Loss not decreasing after first epoch

**Solution**:
1. Check learning rate (might be too low)
2. Verify training data quality
3. Ensure gradient accumulation is working

### Model Generates Nonsense

**Symptom**: Sanity prompt responses are gibberish

**Possible Causes**:
1. **Training diverged**: Check TensorBoard for loss spikes
2. **LoRA rank too high**: Use lower rank
3. **Learning rate too high**: Reduce LR

**Solution**: Rollback and retrain with adjusted hyperparameters

### Adapter Promotion Failed

**Symptom**: "Adapter not found in registry"

**Solution**:
```bash
# Check adapter exists
ls adapters/lora_20260105_142301

# Check registry
cat models/registry.json

# Re-evaluate to add to registry
python scripts/eval_lora.py --run-id lora_20260105_142301
```

---

## Example Commands

### Daily Quick Update

```bash
# Light config for fast iteration
python scripts/export_training_data.py --days 7
python scripts/train_lora.py --config training/configs/lora_light.yaml
python scripts/eval_lora.py --run-id lora_$(date +%Y%m%d_%H%M%S)
```

### Weekly Retraining

```bash
# Balanced config
python scripts/export_training_data.py --days 30
python scripts/train_lora.py --config training/configs/lora_default.yaml
RUN_ID=$(ls -t adapters/ | head -1)
python scripts/eval_lora.py --run-id $RUN_ID
python scripts/promote_adapter.py $RUN_ID --to-production
```

### Monthly Comprehensive

```bash
# Heavy config for maximum adaptation
python scripts/export_training_data.py --days 90
python scripts/train_lora.py --config training/configs/lora_heavy.yaml
RUN_ID=$(ls -t adapters/ | head -1)
python scripts/eval_lora.py --run-id $RUN_ID
```

### Emergency Rollback

```bash
# Immediately restore previous adapter
python scripts/promote_adapter.py --rollback
scripts/stop_all.sh && scripts/start_all.sh
```

---

## Best Practices

1. **Test before production**: Always review metrics and sanity responses
2. **Keep archives**: Don't delete old adapters (enables rollback)
3. **Monitor divergence**: Watch eval loss vs train loss in TensorBoard
4. **Regular retraining**: Weekly with default config recommended
5. **Version control**: Commit training configs to git
6. **Document changes**: Note why you promoted/rolled back in git commits

---

## See Also

- [Memory System](./MEMORY.md) - Understanding conversation storage
- [Semantic Embeddings](./SEMANTIC_EMBEDDINGS_DOD_CHECKLIST.md) - Memory retrieval
- Source code:
  - [scripts/export_training_data.py](../scripts/export_training_data.py)
  - [scripts/train_lora.py](../scripts/train_lora.py)
  - [scripts/eval_lora.py](../scripts/eval_lora.py)
  - [scripts/promote_adapter.py](../scripts/promote_adapter.py)

---

**Last Updated**: 2026-01-05
