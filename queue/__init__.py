"""Queue compatibility shim with Milton job queue API."""
from __future__ import annotations

from pathlib import Path
import importlib.util
import sysconfig

_stdlib_queue = None
_stdlib_names: list[str] = []

try:
    stdlib_path = sysconfig.get_path("stdlib")
    if stdlib_path:
        queue_path = Path(stdlib_path) / "queue.py"
        if queue_path.exists():
            spec = importlib.util.spec_from_file_location("_stdlib_queue", queue_path)
            if spec and spec.loader:
                _stdlib_queue = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(_stdlib_queue)
                for name in dir(_stdlib_queue):
                    if name.startswith("_"):
                        continue
                    globals()[name] = getattr(_stdlib_queue, name)
                _stdlib_names = [name for name in dir(_stdlib_queue) if not name.startswith("_")]
except Exception:
    _stdlib_queue = None
    _stdlib_names = []

from . import api

__all__ = ["api"] + _stdlib_names
