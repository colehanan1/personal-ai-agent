# Milton Deployment Quick Start

## 5-Minute Setup

### 1. Install Systemd Timer
```bash
mkdir -p ~/.config/systemd/user
cp systemd/milton-autobench@.service ~/.config/systemd/user/
cp systemd/milton-autobench@.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now milton-autobench@$USER.timer
loginctl enable-linger $USER
```

### 2. Verify Timer is Running
```bash
systemctl --user list-timers
# Should show milton-autobench@*.timer with next run time
```

### 3. Manual Benchmark (Optional)
```bash
# Quick test (no inference)
python scripts/run_autobench.py

# Full benchmark with live inference
python scripts/run_autobench.py --run-inference
```

### 4. View Results
```bash
python scripts/view_benchmark_results.py
```

### 5. Deploy Best Model
```bash
# Dry-run first
python scripts/deploy_best_model.py --dry-run

# Actual deployment
python scripts/deploy_best_model.py --target-path /path/to/deployment
```

## Common Commands

| Task | Command |
|------|---------|
| Run benchmark | `python scripts/run_autobench.py --run-inference` |
| View results | `python scripts/view_benchmark_results.py` |
| Deploy model | `python scripts/deploy_best_model.py` |
| Check timer | `systemctl --user status milton-autobench@$USER.timer` |
| View logs | `journalctl --user -u milton-autobench@$USER.service -f` |
| Run tests | `python -m pytest tests/benchmarks/ tests/deployment/` |

## File Locations

- Benchmarks: `~/.local/state/milton/benchmarks/runs/`
- Bundles: `~/.local/state/milton/bundles/`
- Deployments: `~/.local/state/milton/deployments/`
- History: `~/.local/state/milton/deployment_history/`

## Expected Output

### Benchmark Results
```
Run ID: benchmark_20260111_195651
Candidates: 3

Model: v1.20260111.1425
  latency_ms: 14.83 (ok)
  tokens_per_sec: 81.15 (ok)
  cove_pass_rate: 100.0 (ok)
  retrieval_score: 65.3 (ok)
```

### Deployment
```
✅ Selected model: v1.20260111.1425
📦 Creating edge bundle...
✅ Bundle created: milton_edge_bundle_v1.20260111.1425_20260111_150643.tar.gz
   Size: 15234.56 MB
🚀 Deploying bundle...
✅ Deployment successful
   Deployment ID: deploy_v1.20260111.1425_20260111_150643_789
   Target path: /deployments/...
   Checksum verified: True
   Load test passed: True
```

## Troubleshooting

**Timer not running?**
```bash
loginctl enable-linger $USER
systemctl --user restart milton-autobench@$USER.timer
```

**Deployment slow?**
- Large models (15GB+) take 2-5 minutes for SHA256 checksums
- This is normal and expected

**No passing candidates?**
- Check benchmark metrics meet thresholds (CoVe ≥90%, retrieval ≥50%)
- Run with `--run-inference` for real metrics

## Next Steps

1. Let timer run for 6 hours
2. Check benchmark results accumulate
3. Review deployment history
4. Configure custom selection weights if needed

Full documentation: `deployment/README.md` and `PHASE4_COMPLETE.md`
