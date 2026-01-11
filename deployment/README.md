# Milton Deployment Infrastructure

This document describes Phase 4 Sub-Prompt 5/5: Edge bundle packaging, deployment manager, and automated scheduling.

## Overview

The deployment infrastructure provides:

1. **Edge Bundle Packaging** - Creates self-contained `.tar.gz` bundles with model files, metadata, and checksums
2. **Deployment Manager** - Validates and deploys bundles to target paths with checksum verification and load testing
3. **Deployment Script** - End-to-end automation: benchmark → select → package → deploy
4. **Systemd Integration** - Automated benchmarking on schedule (every 6 hours by default)

## Architecture

```
┌─────────────────┐
│  Benchmarks     │  Periodic automated benchmarking (systemd timer)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Model Selector │  Selects best model using weighted scoring
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Edge Packager  │  Creates bundle with checksums
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Deployment     │  Validates and deploys to target
│  Manager        │
└─────────────────┘
```

## Components

### 1. Edge Bundle Packager

**File**: `deployment/edge_packager.py`

Creates self-contained bundles with:
- Model files (all weights, configs, tokenizers)
- Registry metadata (version, base model, quantization, etc.)
- Benchmark summary (metrics, scores, timestamp)
- SHA256 checksums for all files
- Manifest with bundle metadata

**Bundle Structure**:
```
bundle_v1.0.0_20260111_150000/
├── model/                    # Complete model directory
│   ├── config.json
│   ├── tokenizer_config.json
│   └── *.safetensors
├── manifest.json             # Bundle metadata
├── registry_entry.json       # Model registry entry
├── benchmark_summary.json    # Benchmark results
└── SHA256SUMS                # File checksums
```

**Usage**:
```python
from deployment.edge_packager import EdgePackager

packager = EdgePackager()
bundle_path = packager.create_bundle(
    model_path=Path("/path/to/model"),
    registry_entry={"version": "v1.0.0", ...},
    benchmark_summary={"score": 0.95, ...}
)

# Extract manifest without unpacking entire bundle
manifest = packager.extract_manifest(bundle_path)

# List all available bundles
bundles = packager.list_bundles()
```

**Bundle Naming**: `milton_edge_bundle_<version>_<timestamp>.tar.gz`

**Storage**: `~/.local/state/milton/bundles/`

### 2. Deployment Manager

**File**: `deployment/deployment_manager.py`

Handles bundle deployment with validation:

1. **Checksum Verification** - Validates all files match SHA256SUMS
2. **Load Test** - Verifies model files are valid (config.json, tokenizer, etc.)
3. **Deployment** - Extracts to target path
4. **History Tracking** - Records all deployments with status

**Usage**:
```python
from deployment.deployment_manager import DeploymentManager

manager = DeploymentManager()

# Deploy bundle with validation
record = manager.deploy_bundle(
    bundle_path=Path("/path/to/bundle.tar.gz"),
    target_path=Path("/target/deployment"),
    dry_run=False,  # Set True to validate without deploying
    verify_checksums=True,
    run_load_test=True
)

# Check deployment status
if record.status == "success":
    print(f"Deployed to {record.target_path}")
else:
    print(f"Deployment failed: {record.error_message}")

# List deployment history
deployments = manager.list_deployments()

# Rollback to previous deployment
rollback = manager.rollback_to_previous()
```

**Deployment Record**:
```json
{
  "deployment_id": "deploy_v1.0.0_20260111_150000_123",
  "timestamp": "2026-01-11T15:00:00.123456",
  "bundle_id": "bundle_v1.0.0_20260111_145959",
  "model_version": "v1.0.0",
  "target_path": "/deployments/deploy_v1.0.0_20260111_150000",
  "status": "success",
  "checksum_verified": true,
  "load_test_passed": true,
  "error_message": null
}
```

**Storage**:
- Deployments: `~/.local/state/milton/deployments/`
- History: `~/.local/state/milton/deployment_history/`

### 3. Deployment Script

**File**: `scripts/deploy_best_model.py`

End-to-end automation script:

```bash
# Dry-run (validate only)
python scripts/deploy_best_model.py --dry-run

# Deploy with latest benchmark
python scripts/deploy_best_model.py

# Deploy with specific benchmark
python scripts/deploy_best_model.py \
    --benchmark-file benchmark_20260111_195651.json

# Deploy to custom path
python scripts/deploy_best_model.py \
    --target-path /custom/deployment/path

# Skip validations (not recommended)
python scripts/deploy_best_model.py \
    --skip-checksum \
    --skip-load-test
```

**Flow**:
1. Find latest benchmark (or use specified file)
2. Load benchmark results
3. Select best model using ModelSelector
4. Get model path from registry
5. Create edge bundle
6. Deploy bundle with validation
7. Record deployment

**Output**:
```
Using benchmark: benchmark_20260111_195651.json
Run ID: benchmark_20260111_195651
Candidates: 3

✅ Selected model: v1.20260111.1425

📊 Metrics:
   latency_ms: 14.83 ms (ok)
   tokens_per_sec: 81.15 tok/s (ok)
   cove_pass_rate: 100.00% (ok)
   retrieval_score: 65.33% (ok)

📂 Model path: /path/to/model

📦 Creating edge bundle...
✅ Bundle created: milton_edge_bundle_v1.20260111.1425_20260111_150643.tar.gz
   Size: 15234.56 MB

🚀 Deploying bundle...
✅ Deployment successful
   Deployment ID: deploy_v1.20260111.1425_20260111_150643_789
   Target path: /deployments/deploy_v1.20260111.1425_20260111_150643_789
   Checksum verified: True
   Load test passed: True
```

### 4. Systemd Integration

**Files**:
- `systemd/milton-autobench@.service` - Service unit
- `systemd/milton-autobench@.timer` - Timer unit
- `systemd/README.md` - Installation guide

**Installation**:
```bash
# Copy units to user systemd directory
mkdir -p ~/.config/systemd/user
cp systemd/milton-autobench@.service ~/.config/systemd/user/
cp systemd/milton-autobench@.timer ~/.config/systemd/user/

# Reload and enable
systemctl --user daemon-reload
systemctl --user enable milton-autobench@$USER.timer
systemctl --user start milton-autobench@$USER.timer

# Enable lingering (run when not logged in)
loginctl enable-linger $USER
```

**Schedule**: Runs every 6 hours (00:00, 06:00, 12:00, 18:00) with:
- 30-minute randomized delay to avoid thundering herd
- Persistent across reboots
- 5-minute post-boot delay

**Management**:
```bash
# Check status
systemctl --user status milton-autobench@$USER.timer
systemctl --user list-timers

# Run manually
systemctl --user start milton-autobench@$USER.service

# View logs
journalctl --user -u milton-autobench@$USER.service -f

# Disable
systemctl --user stop milton-autobench@$USER.timer
systemctl --user disable milton-autobench@$USER.timer
```

**Resource Limits**:
- Memory: 8GB max
- CPU: 400% (4 cores)
- Disk: Read-write access to `~/.local/state/milton/`

## Data Flow

### Complete Autobench → Deployment Flow

1. **Timer Triggers** (systemd)
   - Runs `scripts/run_autobench.py --run-inference`
   - Generates timestamped benchmark results

2. **Benchmark Execution**
   - Enumerates models from registry
   - Runs inference benchmarks (latency, throughput)
   - Evaluates CoVe reasoning
   - Evaluates retrieval quality
   - Writes results to JSON

3. **Model Selection** (on-demand via deploy script)
   - Loads benchmark results
   - Applies weighted scoring
   - Enforces thresholds
   - Selects best candidate

4. **Bundle Creation**
   - Copies model files
   - Computes SHA256 checksums
   - Creates manifest
   - Compresses to .tar.gz

5. **Deployment**
   - Extracts bundle
   - Verifies checksums
   - Runs load test
   - Copies to target path
   - Records deployment

## File Locations

| Purpose | Path |
|---------|------|
| Benchmark results | `~/.local/state/milton/benchmarks/runs/` |
| Edge bundles | `~/.local/state/milton/bundles/` |
| Deployments | `~/.local/state/milton/deployments/` |
| Deployment history | `~/.local/state/milton/deployment_history/` |
| Model registry | `~/.local/state/milton/models/registry.json` |

## Testing

### Unit Tests

**Deployment Tests**: 33 tests covering:
- Bundle manifest serialization
- Bundle creation and extraction
- SHA256 checksum computation
- Deployment validation (checksums, load test)
- Deployment history and rollback
- Error handling

```bash
# Run deployment tests
python -m pytest tests/deployment/ -v

# Run all Phase 4 tests
python -m pytest tests/benchmarks/ tests/deployment/ -v
```

**Test Coverage**:
- ✅ Bundle creation with model files
- ✅ Manifest extraction without unpacking
- ✅ Checksum verification (success and failure)
- ✅ Load test (valid and invalid models)
- ✅ Deployment in dry-run mode
- ✅ Actual deployment to filesystem
- ✅ Deployment history tracking
- ✅ Rollback to previous deployment
- ✅ Error handling (missing files, corrupted data)

### Integration Testing

**End-to-End Test**:
```bash
# 1. Run benchmark
python scripts/run_autobench.py --run-inference

# 2. Deploy (dry-run)
python scripts/deploy_best_model.py --dry-run

# 3. Deploy (actual)
python scripts/deploy_best_model.py --target-path /tmp/test_deployment

# 4. Verify deployment
ls -lh /tmp/test_deployment/
cat /tmp/test_deployment/manifest.json
```

## Performance Notes

### Bundle Creation Time

Bundle creation involves:
1. Copying all model files (~15GB for typical LLM)
2. Computing SHA256 for every file
3. Creating tarball with gzip compression

**Typical timings**:
- Small model (<1GB): ~5-10 seconds
- Medium model (5GB): ~30-60 seconds
- Large model (15GB): ~2-5 minutes

**Optimization tips**:
- Bundle creation is CPU-bound (SHA256 computation)
- Use SSD storage for faster I/O
- Consider parallel checksum computation for very large models
- For production, pre-compute checksums during model creation

### Deployment Time

- Bundle extraction: Fast (gzip decompression)
- Checksum verification: ~1-2 minutes for 15GB model
- Load test: <1 second (just validates JSON files)

**Total deployment time**: 2-7 minutes for typical models

## Security Considerations

1. **Checksum Verification** - All files verified against SHA256SUMS before deployment
2. **Load Testing** - Model files validated before activation
3. **Systemd Hardening**:
   - `NoNewPrivileges=true` - Cannot gain new privileges
   - `PrivateTmp=true` - Private /tmp directory
   - `ProtectSystem=strict` - Read-only system directories
   - `ProtectHome=read-only` - Read-only home (except state dir)

4. **Rollback Capability** - Can revert to previous deployment if issues detected

## Troubleshooting

### Bundle Creation Hangs

**Symptom**: `create_bundle()` runs for >10 minutes

**Cause**: Large model (15GB+) with many files

**Solution**: Be patient - SHA256 computation is CPU-intensive. Monitor with `ps aux | grep python`.

### Deployment Fails: Checksum Mismatch

**Symptom**: `Checksum verification failed`

**Causes**:
- Corrupted bundle (incomplete download/transfer)
- Model files modified after bundle creation
- Disk errors during extraction

**Solution**: Re-create bundle from source model.

### Systemd Timer Not Running

**Symptom**: Timer is enabled but never runs

**Checks**:
```bash
# Verify timer is active
systemctl --user is-active milton-autobench@$USER.timer

# Check next run time
systemctl --user list-timers

# Check for errors
journalctl --user -u milton-autobench@$USER.timer --since today

# Verify lingering (for non-interactive runs)
loginctl show-user $USER | grep Linger
```

**Common fixes**:
- Enable lingering: `loginctl enable-linger $USER`
- Check paths in service file match your installation
- Verify Python environment is accessible

### Load Test Fails

**Symptom**: `Load test failed: Missing essential file`

**Causes**:
- Incomplete model (missing config.json or tokenizer)
- Invalid JSON in config files
- Wrong model format

**Solution**: Verify source model is complete and valid before bundling.

## Future Enhancements

1. **Tailscale Integration** - Remote deployment to edge devices
2. **Multi-device Deployment** - Deploy to multiple targets simultaneously
3. **Health Monitoring** - Post-deployment health checks with automatic rollback
4. **Incremental Bundles** - Delta updates for model versions
5. **Compression Options** - Configurable compression levels
6. **Parallel Checksums** - Speed up large model bundling
7. **Bundle Signing** - Cryptographic signatures for authenticity

## Related Documentation

- [Benchmark System](../benchmarks/README.md)
- [Model Registry](../training/README.md)
- [Model Selection Policy](./SELECTION_POLICY.md)
- [Systemd Integration](../systemd/README.md)
