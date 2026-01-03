# Milton Job Queue System

**Status**: Production-ready (exactly-once semantics, atomic operations)
**Queue Type**: File-based with file locking (fcntl)
**Scope**: Single-user only (no multi-user isolation)

---

## Table of Contents

1. [Overview](#overview)
2. [Job Lifecycle](#job-lifecycle)
3. [Storage Layout](#storage-layout)
4. [API Reference](#api-reference)
5. [Job Processor](#job-processor)
6. [Concurrency Guarantees](#concurrency-guarantees)
7. [Troubleshooting](#troubleshooting)
8. [Testing](#testing)

---

## Overview

The Milton job queue is a file-based overnight job processing system that ensures exactly-once execution semantics. Jobs are submitted to the queue, processed by CORTEX during off-hours, and archived with full provenance.

**Key Features:**
- **Exactly-once processing**: File locking prevents duplicate execution
- **Idempotent**: Reruns don't reprocess completed/failed jobs
- **Atomic state transitions**: No partial updates or race conditions
- **Priority support**: critical > high > medium > low
- **Failed job archival**: Errors are preserved for debugging
- **Concurrent-safe**: Multiple workers can enqueue without collisions

**Implementation**: [queue/api.py](../queue/api.py)

---

## Job Lifecycle

Jobs progress through the following states with atomic transitions:

```
[New Job]
    ↓
  queued ────────────────────────┐
    ↓                             │
in_progress                       │
    ↓                             │
completed ──→ archive/            │
    OR                            │
  failed ────→ archive/ ←─────────┘
```

### State Definitions

| State | Description | Location | Can Retry? |
|-------|-------------|----------|------------|
| `queued` | Job submitted, waiting for processing | `tonight/` | Yes |
| `in_progress` | Job claimed by worker, executing | `tonight/` | No (locked) |
| `completed` | Job finished successfully | `archive/` | No |
| `failed` | Job failed with error | `archive/` | No |

### Atomic Transitions

**queued → in_progress**:
- Implemented by `dequeue_ready_jobs()`
- Uses file locking (`fcntl.LOCK_EX`) to claim jobs atomically
- Multiple workers cannot claim the same job

**in_progress → completed**:
- Implemented by `mark_done()`
- Atomically writes to archive/, then deletes from tonight/
- Uses `os.replace()` for atomic file move

**in_progress → failed**:
- Implemented by `mark_failed()`
- Atomically writes to archive/, then deletes from tonight/
- Preserves error message and stack trace

---

## Storage Layout

Jobs are stored as JSON files in a file-based queue under `STATE_DIR/job_queue/`:

```
~/.local/state/milton/job_queue/
├── tonight/                 # Active queue
│   ├── job-20260102-001.json
│   ├── job-20260102-002.json
│   └── ...
├── archive/                 # Completed/failed jobs
│   ├── job-20260101-001.json
│   ├── job-20260101-002.json
│   └── ...
└── .queue.lock             # Global queue lock (for job ID generation)
```

### Job File Format

```json
{
  "job_id": "job-20260102-001",
  "type": "code_generation",
  "payload": {
    "task": "Implement user authentication system"
  },
  "priority": "high",
  "status": "completed",
  "created_at": "2026-01-02T10:30:00+00:00",
  "run_at": "2026-01-02T22:30:00+00:00",
  "started_at": "2026-01-02T22:30:05+00:00",
  "completed_at": "2026-01-02T22:35:42+00:00",
  "updated_at": "2026-01-02T22:35:42+00:00",
  "artifacts": [
    "milton/auth/models.py",
    "milton/auth/routes.py"
  ],
  "result": {
    "task_id": "job-20260102-001",
    "status": "completed",
    "output": "Authentication system implemented successfully",
    "output_paths": ["milton/auth/models.py", "milton/auth/routes.py"],
    "evidence_refs": ["test:auth_001", "test:auth_002"]
  },
  "events": [
    {
      "timestamp": "2026-01-02T10:30:00+00:00",
      "event": "enqueued",
      "status": "queued",
      "priority": "high"
    },
    {
      "timestamp": "2026-01-02T22:30:05+00:00",
      "event": "claimed",
      "status": "in_progress",
      "pid": 12345
    },
    {
      "timestamp": "2026-01-02T22:35:42+00:00",
      "event": "completed",
      "status": "completed",
      "artifact_count": 2
    }
  ]
}
```

### Failed Job Format

```json
{
  "job_id": "job-20260102-003",
  "type": "code_generation",
  "status": "failed",
  "error": "LLM API timeout after 120 seconds",
  "failed_at": "2026-01-02T22:32:15+00:00",
  ...
}
```

---

## API Reference

### Enqueue Job

```python
import milton_queue as queue_api
from datetime import datetime, timedelta

job_id = queue_api.enqueue_job(
    job_type="code_generation",
    payload={"task": "Implement feature X"},
    priority="high",  # low, medium, high, critical
    run_at=datetime.now() + timedelta(hours=12),  # Optional
)
```

**Parameters:**
- `job_type` (str, required): Type of job (e.g., "code_generation", "research")
- `payload` (dict, required): Job data (must include "task" field)
- `priority` (str, default="medium"): Job priority (low/medium/high/critical)
- `run_at` (datetime, optional): When to run (defaults to now)
- `base_dir` (Path, optional): Queue directory (defaults to STATE_DIR)
- `now` (datetime, optional): Current time (for testing)

**Returns:** Job ID (str)

### Dequeue Ready Jobs

```python
jobs = queue_api.dequeue_ready_jobs(
    now=datetime.now(timezone.utc),
    base_dir=None,  # Defaults to STATE_DIR
)
```

**Behavior:**
- Atomically claims jobs with file locking
- Marks claimed jobs as `in_progress`
- Returns jobs in priority order (critical → low)
- Jobs with `run_at` in the future are skipped
- Already claimed jobs are skipped (non-blocking lock)

**Returns:** List of job dicts

### Mark Job Completed

```python
queue_api.mark_done(
    job_id="job-20260102-001",
    artifact_paths=["output.txt", "result.json"],
    result={"status": "completed", "output": "Success"},
)
```

**Behavior:**
- Updates job status to `completed`
- Atomically moves job to `archive/`
- Preserves artifact paths and result

### Mark Job Failed

```python
queue_api.mark_failed(
    job_id="job-20260102-002",
    error="Task execution failed: invalid input",
)
```

**Behavior:**
- Updates job status to `failed`
- Atomically moves job to `archive/`
- Preserves error message for debugging

---

## Job Processor

The job processor ([scripts/job_processor.py](../scripts/job_processor.py)) runs as a systemd timer and processes queued jobs with CORTEX.

### Usage

**Manual run:**
```bash
python scripts/job_processor.py
```

**Systemd timer:**
```bash
systemctl --user enable milton-job-processor.timer
systemctl --user start milton-job-processor.timer
```

### Processing Logic

```python
from agents.cortex import CORTEX
from agents.contracts import TaskResult, TaskStatus
import milton_queue as queue_api

# Claim ready jobs
jobs = queue_api.dequeue_ready_jobs()

cortex = CORTEX()

for job in jobs:
    # Execute with CORTEX
    result = cortex.process_overnight_job({
        'id': job['job_id'],
        'task': job['task'],
    })

    # Handle result
    if result.status == TaskStatus.COMPLETED:
        queue_api.mark_done(
            job['job_id'],
            artifact_paths=result.output_paths,
            result=result.to_dict(),
        )
    else:
        queue_api.mark_failed(
            job['job_id'],
            error=result.error_message,
        )
```

### Logs

Logs are written to `STATE_DIR/logs/cortex/processor_YYYYMMDD_HHMMSS.log`.

Example log output:
```
2026-01-02 22:30:00 [INFO] Starting CORTEX overnight job queue processing
2026-01-02 22:30:00 [INFO] State directory: /home/user/.local/state/milton
2026-01-02 22:30:00 [INFO] Found 3 job(s) ready to process
2026-01-02 22:30:00 [INFO] Processing job: job-20260102-001
2026-01-02 22:30:00 [INFO] Task: Implement user authentication...
2026-01-02 22:30:00 [INFO] Executing with CORTEX...
2026-01-02 22:35:00 [INFO] Status: completed
2026-01-02 22:35:00 [INFO] Output paths: ['milton/auth/models.py']
2026-01-02 22:35:00 [INFO] Evidence refs: ['test:auth_001']
2026-01-02 22:35:00 [INFO] ✓ Job completed and archived
```

---

## Concurrency Guarantees

The job queue provides the following concurrency guarantees:

### 1. No ID Collisions

**Mechanism**: Global queue lock (`_queue_lock()`) during job ID generation.

```python
with _queue_lock(base_dir):
    job_id = _next_job_id(timestamp, base_dir)
    _write_job(job_path, record)
```

**Test**: [test_concurrent_enqueue_no_collisions](../tests/test_job_queue_concurrency.py)

### 2. Exactly-Once Processing

**Mechanism**: File locking (`fcntl.LOCK_EX`) when claiming jobs.

```python
with _locked_file(job_path, mode="r+", blocking=False) as handle:
    if handle is None:
        continue  # Job already locked
    record["status"] = "in_progress"
    _write_job_handle(handle, record)
```

**Test**: [test_dequeue_exactly_once](../tests/test_job_queue_concurrency.py)

### 3. No Duplicate Processing

**Mechanism**: Non-blocking locks ensure workers skip already-claimed jobs.

**Test**: [test_concurrent_dequeue_no_duplicates](../tests/test_job_queue_concurrency.py)

### 4. Atomic Archival

**Mechanism**: Write-then-delete with `os.replace()` for atomic file moves.

```python
# Write to archive first
_write_job(archive_path, record)
# Then remove from queue
job_path.unlink(missing_ok=True)
```

**Test**: [test_mark_done_archives_job](../tests/test_job_queue_concurrency.py)

### 5. Idempotency

**Mechanism**: Archived jobs (completed/failed) are never reprocessed.

**Test**: [test_idempotent_processing](../tests/test_job_queue_concurrency.py)

---

## Troubleshooting

### Problem: Jobs not being processed

**Check**:
1. Is the job processor running?
   ```bash
   systemctl --user status milton-job-processor.timer
   systemctl --user status milton-job-processor.service
   ```

2. Are there jobs in the queue?
   ```bash
   ls ~/.local/state/milton/job_queue/tonight/
   ```

3. Check job status in JSON file:
   ```bash
   cat ~/.local/state/milton/job_queue/tonight/job-*.json | jq '.status'
   ```

4. Check processor logs:
   ```bash
   tail -f ~/.local/state/milton/logs/cortex/processor_*.log
   ```

### Problem: Jobs stuck in `in_progress`

**Cause**: Worker crashed or was killed before completing job.

**Solution**:
1. Check if worker is still running:
   ```bash
   ps aux | grep job_processor
   ```

2. If no worker is running, manually update job status:
   ```python
   import json
   from pathlib import Path

   job_file = Path("~/.local/state/milton/job_queue/tonight/job-XXX.json").expanduser()

   with job_file.open() as f:
       job = json.load(f)

   job["status"] = "queued"  # Reset to queued
   job["updated_at"] = datetime.now(timezone.utc).isoformat()

   with job_file.open("w") as f:
       json.dump(job, f, indent=2)
   ```

3. Or delete the job file to skip it:
   ```bash
   rm ~/.local/state/milton/job_queue/tonight/job-XXX.json
   ```

### Problem: Job fails repeatedly

**Check archived job for error**:
```bash
cat ~/.local/state/milton/job_queue/archive/job-*.json | jq '.error'
```

**Common errors:**
- `LLM API timeout`: vLLM server not running or overloaded
- `Task execution failed`: Invalid task description or missing dependencies
- `File not found`: Incorrect paths in task payload

### Problem: Old jobs piling up in archive

**Solution**: Implement archive cleanup script:

```python
from pathlib import Path
from datetime import datetime, timedelta

archive_dir = Path("~/.local/state/milton/job_queue/archive").expanduser()
cutoff = datetime.now() - timedelta(days=30)

for job_file in archive_dir.glob("*.json"):
    if job_file.stat().st_mtime < cutoff.timestamp():
        job_file.unlink()
```

### Problem: Concurrent job submissions causing errors

**Check**: This should not happen! File locking prevents collisions.

**Debug**:
1. Verify `fcntl` is available:
   ```python
   import fcntl
   print(fcntl)  # Should not error
   ```

2. Check file system supports locking:
   ```bash
   # Most Linux filesystems support fcntl locking
   mount | grep $(df ~/.local/state/milton | tail -1 | awk '{print $1}')
   ```

3. Run concurrency tests:
   ```bash
   pytest tests/test_job_queue_concurrency.py -v
   ```

---

## Testing

### Unit Tests

```bash
# Run all job queue tests
pytest tests/test_job_queue_concurrency.py -v
```

### Integration Test (25 jobs)

```bash
pytest tests/test_job_queue_concurrency.py::test_full_integration_20_jobs -v
```

**What it tests:**
- Enqueues 25 jobs concurrently
- Processes with simulated CORTEX
- Verifies exactly-once execution
- Checks artifact preservation
- Validates failed job archival
- Confirms idempotency on reruns

### Manual Concurrency Test

**Reproduce concurrency check:**

1. Create test script `test_concurrent_jobs.py`:
   ```python
   import milton_queue as queue_api
   from concurrent.futures import ThreadPoolExecutor
   from datetime import datetime, timezone

   def enqueue_job(i):
       return queue_api.enqueue_job(
           job_type="stress_test",
           payload={"task": f"Stress test job {i}"},
           priority="medium",
       )

   # Enqueue 50 jobs concurrently from 10 workers
   with ThreadPoolExecutor(max_workers=10) as executor:
       job_ids = list(executor.map(enqueue_job, range(50)))

   print(f"Enqueued {len(job_ids)} jobs")
   print(f"Unique IDs: {len(set(job_ids))}")
   assert len(job_ids) == len(set(job_ids)), "ID collision detected!"

   # Verify all jobs in queue
   jobs = queue_api.dequeue_ready_jobs(now=datetime.now(timezone.utc))
   print(f"Dequeued {len(jobs)} jobs")
   assert len(jobs) == 50, f"Expected 50 jobs, got {len(jobs)}"
   ```

2. Run:
   ```bash
   python test_concurrent_jobs.py
   ```

3. Expected output:
   ```
   Enqueued 50 jobs
   Unique IDs: 50
   Dequeued 50 jobs
   ```

4. Verify idempotency:
   ```python
   # Second dequeue should return empty
   jobs_second = queue_api.dequeue_ready_jobs(now=datetime.now(timezone.utc))
   assert len(jobs_second) == 0, "Jobs processed twice!"
   ```

---

## Performance Characteristics

| Operation | Complexity | Notes |
|-----------|------------|-------|
| `enqueue_job` | O(n) | Scans queue for max ID (cached in production) |
| `dequeue_ready_jobs` | O(n log n) | Scans + sorts by priority |
| `mark_done` | O(1) | Single file write + delete |
| `mark_failed` | O(1) | Single file write + delete |

**Recommended limits:**
- Max active jobs in `tonight/`: 1000
- Max concurrent workers: 10
- Archive retention: 30 days

---

## References

- [queue/api.py](../queue/api.py) - Queue implementation
- [scripts/job_processor.py](../scripts/job_processor.py) - Job processor
- [agents/cortex.py](../agents/cortex.py) - CORTEX agent
- [agents/contracts.py](../agents/contracts.py) - TaskResult contract
- [tests/test_job_queue_concurrency.py](../tests/test_job_queue_concurrency.py) - Integration tests

---

**Last Updated**: 2026-01-02
**Maintainer**: Cole Hanan
**Status**: Production-ready (exactly-once semantics verified)
