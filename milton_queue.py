"""Wrapper for Milton job queue API without stdlib queue conflicts."""
from __future__ import annotations

from pathlib import Path
import importlib.util

_QUEUE_API_PATH = Path(__file__).resolve().parent / "queue" / "api.py"

_spec = importlib.util.spec_from_file_location("milton_queue_api", _QUEUE_API_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError("Unable to load Milton queue API")

_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

enqueue_job = _module.enqueue_job
dequeue_ready_jobs = _module.dequeue_ready_jobs
mark_done = _module.mark_done

__all__ = ["enqueue_job", "dequeue_ready_jobs", "mark_done"]
