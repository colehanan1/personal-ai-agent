# Milton Benchmarking Infrastructure

Automated benchmarking system for tracking model performance across the Milton model registry.

## Overview

The benchmark infrastructure provides:
- **Strict JSON schema** for reproducible benchmark results
- **Automatic enumeration** of models from the registry
- **Comprehensive metrics** with proper error tracking
- **System information** capture for reproducibility

## Quick Start

Run a dry-run benchmark (enumerates models without executing tests):

```bash
python scripts/run_autobench.py --dry-run
```

View the results:

```bash
cat ~/.local/state/milton/benchmarks/runs/benchmark_*.json | jq
```

## Schema

Each benchmark run produces a JSON file with:

### Metadata
- `run_id`: Unique identifier (format: `benchmark_YYYYMMDD_HHMMSS`)
- `timestamp`: ISO 8601 timestamp
- `git_sha`: Git commit hash
- `git_branch`: Git branch name
- `git_dirty`: Whether there are uncommitted changes
- `command_line`: Command used to run the benchmark
- `dry_run`: Whether this was a dry run

### System Info
- `hostname`: System hostname
- `platform`: OS platform (Linux, Darwin, etc.)
- `python_version`: Python version
- `cpu_info`: CPU model and specs
- `cpu_count`: Number of CPU cores
- `total_ram_gb`: Total system RAM in GB
- `gpu_info`: GPU model (if available)
- `cuda_version`: CUDA version (if available)

### Candidates

Each model candidate includes:
- `version`: Model version identifier
- `model_type`: Type of model (base, quantized, distilled, quantized+distilled)
- `model_path`: Path to model files
- `base_model`: Base model name
- `quantization`: Quantization level (e.g., "4bit", "8bit", "Q4_0")
- `distilled_from`: Source adapter if distilled
- `file_size_mb`: Total size of model files in MB

### Metrics

Each metric has:
- `status`: One of "ok", "skipped", or "error"
- `value`: Numeric value (if status is "ok")
- `error_message`: Error description (if status is "error")
- `metadata`: Additional context

Available metrics:
- `latency_ms`: Inference latency in milliseconds
- `tokens_per_sec`: Throughput in tokens per second
- `peak_vram_mb`: Peak VRAM usage in MB
- `peak_ram_mb`: Peak RAM usage in MB
- `cove_pass_rate`: CoVe validation pass rate
- `retrieval_score`: Retrieval quality score

## Error Handling

The system **never silently fails**. Each metric explicitly tracks:
- **OK**: Metric measured successfully
- **SKIPPED**: Metric skipped (e.g., no backend available)
- **ERROR**: Metric failed with error message

Example error tracking:
```json
{
  "latency_ms": {
    "status": "error",
    "value": null,
    "error_message": "Model path does not exist: /path/to/model",
    "metadata": {}
  }
}
```

## Directory Structure

```
benchmarks/
├── __init__.py           # Package exports
└── schema.py             # Pydantic/dataclass schemas

scripts/
└── run_autobench.py      # Main benchmark runner

tests/benchmarks/
├── test_autobench_schema.py   # Schema validation tests
└── test_autobench_runner.py   # Integration tests

~/.local/state/milton/benchmarks/runs/
└── benchmark_*.json      # Benchmark results
```

## Usage

### Basic Usage

```bash
# Run with default registry
python scripts/run_autobench.py --dry-run

# Specify custom registry
python scripts/run_autobench.py --registry /path/to/registry.json

# Specify output directory
python scripts/run_autobench.py --output-dir /path/to/output

# Enable verbose logging
python scripts/run_autobench.py --verbose
```

### Programmatic Usage

```python
from benchmarks.schema import BenchmarkRun
from scripts.run_autobench import run_benchmark

# Run benchmark
output_path = run_benchmark(dry_run=True)

# Load results
run = BenchmarkRun.load(output_path)

# Access data
print(f"Run ID: {run.metadata.run_id}")
print(f"Candidates: {len(run.candidates)}")

for candidate in run.candidates:
    print(f"  {candidate.version}: {candidate.model_type}")
    if candidate.latency_ms.status == "ok":
        print(f"    Latency: {candidate.latency_ms.value} ms")
```

## Testing

Run all benchmark tests:

```bash
pytest tests/benchmarks/ -v
```

Run specific test suites:

```bash
# Schema tests only
pytest tests/benchmarks/test_autobench_schema.py -v

# Integration tests only
pytest tests/benchmarks/test_autobench_runner.py -v
```

## Next Steps

Phase 4 will extend this infrastructure with:
- Actual metric measurement (latency, throughput, memory)
- CoVe validation integration
- Retrieval quality scoring
- Automated performance comparisons
- CI/CD integration
