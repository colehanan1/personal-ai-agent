"""
Integration tests for job queue concurrency and exactly-once semantics.

Tests that the job queue handles:
- Concurrent job submissions (no drops)
- Exactly-once processing (no duplicates)
- Idempotency (reruns don't reprocess)
- Atomic state transitions
- Failed job archival
"""

import json
import pytest
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from agents.cortex import CORTEX
from agents.contracts import TaskResult, TaskStatus
import milton_queue as queue_api


@pytest.fixture
def test_queue_dir():
    """Create a temporary queue directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        yield base_dir


def test_enqueue_multiple_jobs_no_drops(test_queue_dir):
    """Test that enqueueing multiple jobs doesn't drop any."""
    num_jobs = 25
    job_ids = []

    for i in range(num_jobs):
        job_id = queue_api.enqueue_job(
            job_type="test",
            payload={"task": f"Test task {i}"},
            priority="medium",
            base_dir=test_queue_dir,
        )
        job_ids.append(job_id)

    # All job IDs should be unique
    assert len(job_ids) == num_jobs
    assert len(set(job_ids)) == num_jobs

    # All jobs should exist in tonight/
    tonight_dir = test_queue_dir / "job_queue" / "tonight"
    assert tonight_dir.exists()

    job_files = list(tonight_dir.glob("*.json"))
    assert len(job_files) == num_jobs


def test_concurrent_enqueue_no_collisions(test_queue_dir):
    """Test concurrent job enqueuing doesn't create ID collisions."""
    num_jobs = 30
    job_ids = []

    def enqueue_job(i):
        return queue_api.enqueue_job(
            job_type="concurrent_test",
            payload={"task": f"Concurrent task {i}"},
            priority="medium",
            base_dir=test_queue_dir,
        )

    # Enqueue jobs concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(enqueue_job, i) for i in range(num_jobs)]
        for future in as_completed(futures):
            job_ids.append(future.result())

    # All job IDs should be unique (no collisions)
    assert len(job_ids) == num_jobs
    assert len(set(job_ids)) == num_jobs

    # All jobs should exist
    tonight_dir = test_queue_dir / "job_queue" / "tonight"
    job_files = list(tonight_dir.glob("*.json"))
    assert len(job_files) == num_jobs


def test_dequeue_exactly_once(test_queue_dir):
    """Test that dequeuing processes each job exactly once."""
    num_jobs = 20

    # Enqueue jobs
    for i in range(num_jobs):
        queue_api.enqueue_job(
            job_type="dequeue_test",
            payload={"task": f"Dequeue task {i}"},
            priority="medium",
            base_dir=test_queue_dir,
        )

    # Dequeue all jobs
    now = datetime.now(timezone.utc)
    jobs = queue_api.dequeue_ready_jobs(now=now, base_dir=test_queue_dir)

    # Should get all jobs
    assert len(jobs) == num_jobs

    # All jobs should be marked as in_progress
    for job in jobs:
        assert job["status"] == "in_progress"
        assert "started_at" in job

    # Second dequeue should return empty (already claimed)
    jobs_second = queue_api.dequeue_ready_jobs(now=now, base_dir=test_queue_dir)
    assert len(jobs_second) == 0


def test_concurrent_dequeue_no_duplicates(test_queue_dir):
    """Test concurrent dequeuing doesn't process jobs twice."""
    num_jobs = 25

    # Enqueue jobs
    for i in range(num_jobs):
        queue_api.enqueue_job(
            job_type="concurrent_dequeue_test",
            payload={"task": f"Concurrent dequeue task {i}"},
            priority="medium",
            base_dir=test_queue_dir,
        )

    # Dequeue concurrently from multiple workers
    now = datetime.now(timezone.utc)
    all_jobs = []

    def dequeue_jobs():
        return queue_api.dequeue_ready_jobs(now=now, base_dir=test_queue_dir)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(dequeue_jobs) for _ in range(5)]
        for future in as_completed(futures):
            jobs = future.result()
            all_jobs.extend(jobs)

    # Should have exactly num_jobs (no duplicates)
    assert len(all_jobs) == num_jobs

    # All job IDs should be unique
    job_ids = [job["job_id"] for job in all_jobs]
    assert len(set(job_ids)) == num_jobs


def test_mark_done_archives_job(test_queue_dir):
    """Test that marking a job as done archives it."""
    job_id = queue_api.enqueue_job(
        job_type="archive_test",
        payload={"task": "Test archival"},
        base_dir=test_queue_dir,
    )

    # Dequeue
    jobs = queue_api.dequeue_ready_jobs(
        now=datetime.now(timezone.utc),
        base_dir=test_queue_dir,
    )
    assert len(jobs) == 1

    # Mark done
    queue_api.mark_done(
        job_id,
        artifact_paths=["output.txt"],
        result={"status": "completed"},
        base_dir=test_queue_dir,
    )

    # Job should be in archive, not in tonight
    tonight_dir = test_queue_dir / "job_queue" / "tonight"
    archive_dir = test_queue_dir / "job_queue" / "archive"

    tonight_file = tonight_dir / f"{job_id}.json"
    archive_file = archive_dir / f"{job_id}.json"

    assert not tonight_file.exists()
    assert archive_file.exists()

    # Archived job should have completed status
    with archive_file.open() as f:
        record = json.load(f)

    assert record["status"] == "completed"
    assert record["artifacts"] == ["output.txt"]
    assert "completed_at" in record


def test_mark_failed_archives_job(test_queue_dir):
    """Test that marking a job as failed archives it."""
    job_id = queue_api.enqueue_job(
        job_type="failure_test",
        payload={"task": "Test failure"},
        base_dir=test_queue_dir,
    )

    # Dequeue
    jobs = queue_api.dequeue_ready_jobs(
        now=datetime.now(timezone.utc),
        base_dir=test_queue_dir,
    )
    assert len(jobs) == 1

    # Mark failed
    error_msg = "Test error occurred"
    queue_api.mark_failed(
        job_id,
        error=error_msg,
        base_dir=test_queue_dir,
        now=datetime.now(timezone.utc),
    )

    # Job should be in archive, not in tonight
    tonight_dir = test_queue_dir / "job_queue" / "tonight"
    archive_dir = test_queue_dir / "job_queue" / "archive"

    tonight_file = tonight_dir / f"{job_id}.json"
    archive_file = archive_dir / f"{job_id}.json"

    assert not tonight_file.exists()
    assert archive_file.exists()

    # Archived job should have failed status
    with archive_file.open() as f:
        record = json.load(f)

    assert record["status"] == "failed"
    assert record["error"] == error_msg
    assert "failed_at" in record


def test_idempotent_processing(test_queue_dir):
    """Test that reruns don't reprocess completed/failed jobs."""
    num_jobs = 15

    # Enqueue jobs
    for i in range(num_jobs):
        queue_api.enqueue_job(
            job_type="idempotent_test",
            payload={"task": f"Idempotent task {i}"},
            base_dir=test_queue_dir,
        )

    # First run: process all jobs
    now = datetime.now(timezone.utc)
    jobs_run1 = queue_api.dequeue_ready_jobs(now=now, base_dir=test_queue_dir)
    assert len(jobs_run1) == num_jobs

    # Complete some, fail others
    for i, job in enumerate(jobs_run1):
        if i % 2 == 0:
            queue_api.mark_done(
                job["job_id"],
                artifact_paths=[],
                result={"status": "completed"},
                base_dir=test_queue_dir,
            )
        else:
            queue_api.mark_failed(
                job["job_id"],
                error="Test failure",
                base_dir=test_queue_dir,
                now=now,
            )

    # Second run: should find no jobs (all archived)
    jobs_run2 = queue_api.dequeue_ready_jobs(now=now, base_dir=test_queue_dir)
    assert len(jobs_run2) == 0

    # Verify all jobs are in archive
    archive_dir = test_queue_dir / "job_queue" / "archive"
    archive_files = list(archive_dir.glob("*.json"))
    assert len(archive_files) == num_jobs


def test_priority_ordering(test_queue_dir):
    """Test that jobs are dequeued in priority order."""
    # Enqueue jobs with different priorities
    low_job = queue_api.enqueue_job(
        job_type="priority_test",
        payload={"task": "Low priority"},
        priority="low",
        base_dir=test_queue_dir,
    )

    medium_job = queue_api.enqueue_job(
        job_type="priority_test",
        payload={"task": "Medium priority"},
        priority="medium",
        base_dir=test_queue_dir,
    )

    high_job = queue_api.enqueue_job(
        job_type="priority_test",
        payload={"task": "High priority"},
        priority="high",
        base_dir=test_queue_dir,
    )

    critical_job = queue_api.enqueue_job(
        job_type="priority_test",
        payload={"task": "Critical priority"},
        priority="critical",
        base_dir=test_queue_dir,
    )

    # Dequeue all
    now = datetime.now(timezone.utc)
    jobs = queue_api.dequeue_ready_jobs(now=now, base_dir=test_queue_dir)

    # Should be in priority order: critical, high, medium, low
    job_ids = [job["job_id"] for job in jobs]
    assert job_ids == [critical_job, high_job, medium_job, low_job]


def test_full_integration_20_jobs(test_queue_dir):
    """
    Full integration test: Enqueue 20+ jobs, process with mock CORTEX.

    Verifies:
    - All jobs are processed exactly once
    - Results are persisted with output_paths
    - Failed jobs are captured cleanly
    """
    num_jobs = 25

    # Enqueue jobs
    job_ids = []
    for i in range(num_jobs):
        # Some jobs will "fail" (odd numbered)
        task = f"Integration test task {i}"
        job_id = queue_api.enqueue_job(
            job_type="integration_test",
            payload={"task": task, "should_fail": i % 2 == 1},
            priority="medium",
            base_dir=test_queue_dir,
        )
        job_ids.append(job_id)

    # Process jobs (simulating job_processor.py)
    now = datetime.now(timezone.utc)
    jobs = queue_api.dequeue_ready_jobs(now=now, base_dir=test_queue_dir)

    assert len(jobs) == num_jobs

    processed = 0
    failed = 0

    for job in jobs:
        job_id = job["job_id"]
        payload = job.get("payload", {})
        should_fail = payload.get("should_fail", False)

        try:
            if should_fail:
                # Simulate failure
                raise ValueError(f"Simulated failure for job {job_id}")

            # Simulate success
            result = TaskResult(
                task_id=job_id,
                completed_at=datetime.now(timezone.utc).isoformat(),
                agent="cortex",
                status=TaskStatus.COMPLETED,
                output=f"Completed task for {job_id}",
                output_paths=[f"output_{job_id}.txt"],
                evidence_refs=[f"test_{job_id}"],
            )

            queue_api.mark_done(
                job_id,
                artifact_paths=result.output_paths,
                result=result.to_dict(),
                base_dir=test_queue_dir,
            )
            processed += 1

        except Exception as e:
            queue_api.mark_failed(
                job_id,
                error=str(e),
                base_dir=test_queue_dir,
                now=now,
            )
            failed += 1

    # Verify counts
    assert processed + failed == num_jobs
    assert processed == num_jobs // 2 + 1  # Even numbered jobs (0, 2, 4, ...)
    assert failed == num_jobs // 2  # Odd numbered jobs (1, 3, 5, ...)

    # Verify all jobs are archived
    archive_dir = test_queue_dir / "job_queue" / "archive"
    archive_files = list(archive_dir.glob("*.json"))
    assert len(archive_files) == num_jobs

    # Verify completed jobs have correct structure
    for archive_file in archive_files:
        with archive_file.open() as f:
            record = json.load(f)

        assert record["status"] in ("completed", "failed")

        if record["status"] == "completed":
            assert "result" in record
            assert "output_paths" in record["result"]
            assert len(record["result"]["output_paths"]) > 0
            assert "evidence_refs" in record["result"]
        else:
            assert "error" in record
            assert "Simulated failure" in record["error"]

    # Second run should find no jobs (idempotent)
    jobs_run2 = queue_api.dequeue_ready_jobs(now=now, base_dir=test_queue_dir)
    assert len(jobs_run2) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
