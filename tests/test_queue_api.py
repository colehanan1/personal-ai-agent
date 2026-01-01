from datetime import datetime, timedelta, timezone
import json

import milton_queue as queue_api


def test_queue_lifecycle(tmp_path):
    now = datetime(2025, 1, 2, 22, 0, tzinfo=timezone.utc)
    job_id = queue_api.enqueue_job(
        "cortex_task",
        {"task": "Summarize lab notes"},
        priority="high",
        base_dir=tmp_path,
        now=now,
    )

    job_path = tmp_path / "job_queue" / "tonight" / f"{job_id}.json"
    assert job_path.exists()

    ready = queue_api.dequeue_ready_jobs(now=now, base_dir=tmp_path)
    assert ready
    assert ready[0]["job_id"] == job_id

    record = json.loads(job_path.read_text())
    assert record["status"] == "in_progress"

    done = queue_api.mark_done(
        job_id,
        artifact_paths=["outputs/result.txt"],
        base_dir=tmp_path,
        now=now + timedelta(hours=1),
    )

    assert done["status"] == "completed"
    assert done["artifacts"] == ["outputs/result.txt"]

    archive_path = tmp_path / "job_queue" / "archive" / f"{job_id}.json"
    assert archive_path.exists()
    assert not job_path.exists()
