"""Shared helpers for resolving Milton state paths."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

DEFAULT_STATE_DIR = Path.home() / ".local" / "state" / "milton"


def resolve_state_dir(base_dir: Optional[Path] = None) -> Path:
    """Resolve the Milton base state directory."""
    if base_dir is not None:
        return Path(base_dir).expanduser()
    env_dir = os.getenv("STATE_DIR") or os.getenv("MILTON_STATE_DIR")
    if env_dir:
        return Path(env_dir).expanduser()
    return DEFAULT_STATE_DIR


def resolve_state_subdir(name: str, base_dir: Optional[Path] = None) -> Path:
    """Resolve a named subdirectory within the Milton state directory."""
    return resolve_state_dir(base_dir) / name
