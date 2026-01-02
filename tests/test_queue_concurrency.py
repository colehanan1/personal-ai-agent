from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import multiprocessing as mp
import os
import time

import milton_queue as queue_api


def _queue_worker(
    base_dir: str,
    result_queue: mp.Queue,
    worker_id: int,
    *,
    max_idle_cycles: int = 50,
    poll_interval: float = 0.01,
    max_runtime: float = 10.0,
) -> None:
    base_path = Path(base_dir)
    processed: list[str] = []
    errors: list[dict[str, str | None]] = []
    idle_cycles = 0
    deadline = time.time() + max_runtime

    while idle_cycles < max_idle_cycles and time.time() < deadline:
        jobs = queue_api.dequeue_ready_jobs(
            now=datetime.now(timezone.utc),
            base_dir=base_path,
        )
        if not jobs:
            idle_cycles += 1
            time.sleep(poll_interval)
            continue

        idle_cycles = 0
        for job in jobs:
            job_id = job.get("job_id")
            if not job_id:
                errors.append({"job_id": None, "error": "missing job_id"})
                continue
            try:
                queue_api.mark_done(
                    job_id,
                    artifact_paths=[f"outputs/{job_id}.txt"],
                    result={"worker": worker_id, "pid": os.getpid()},
                    base_dir=base_path,
                    now=datetime.now(timezone.utc),
                )
                processed.append(job_id)
            except Exception as exc:
                errors.append({"job_id": job_id, "error": str(exc)})

    result_queue.put({"processed": processed, "errors": errors})


def test_queue_concurrency_processing(tmp_path: Path) -> None:
    now = datetime(2025, 1, 2, 22, 0, tzinfo=timezone.utc)
    job_ids = [
        queue_api.enqueue_job(
            "cortex_task",
            {"task": f"task-{index}"},
            priority="medium",
            base_dir=tmp_path,
            now=now,
        )
        for index in range(25)
    ]

    ctx = mp.get_context("spawn")
    result_queue: mp.Queue = ctx.Queue()
    workers = [
        ctx.Process(target=_queue_worker, args=(str(tmp_path), result_queue, worker_id))
        for worker_id in range(4)
    ]

    for worker in workers:
        worker.start()

    for worker in workers:
        worker.join(timeout=10)

    for worker in workers:
        if worker.is_alive():
            worker.terminate()
            worker.join()

    assert all(not worker.is_alive() for worker in workers), "Worker deadlock detected"

    results = []
    for _ in workers:
        try:
            results.append(result_queue.get(timeout=2))
        except Exception as exc:
            results.append(
                {"processed": [], "errors": [{"job_id": None, "error": f"missing result: {exc}"}]}
            )

    processed = [job_id for result in results for job_id in result["processed"]]
    errors = [error for result in results for error in result["errors"]]

    assert not errors, f"Worker errors: {errors}"
    assert len(processed) == len(job_ids)
    assert len(processed) == len(set(processed))
    assert set(processed) == set(job_ids)

    archive_dir = tmp_path / "job_queue" / "archive"
    archived = list(archive_dir.glob("*.json"))
    assert len(archived) == len(job_ids)

    for path in archived:
        record = json.loads(path.read_text())
        assert record["status"] == "completed"
        assert record["job_id"] in job_ids
        assert record.get("result")
        assert record.get("artifacts") == [f"outputs/{record['job_id']}.txt"]
        assert any(event.get("event") == "completed" for event in record.get("events", []))
