"""Shared helpers for resolving Milton state paths.

This module provides canonical path resolution for all Milton state files,
preventing split-brain scenarios where different components use different files.
"""
from __future__ import annotations

import os
import json
import sqlite3
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_STATE_DIR = Path.home() / ".local" / "state" / "milton"

# Canonical database filenames
CANONICAL_REMINDERS_DB = "reminders.db"
LEGACY_REMINDERS_DB = "reminders.sqlite3"
MIGRATION_GUARD_FILE = ".reminders_db_migrated"


def resolve_state_dir(base_dir: Optional[Path] = None) -> Path:
    """Resolve the Milton base state directory.

    Handles both ~ and $HOME/$VAR expansion for compatibility with
    systemd EnvironmentFile and shell scripts.
    """
    if base_dir is not None:
        return Path(os.path.expandvars(str(base_dir))).expanduser()
    env_dir = os.getenv("STATE_DIR") or os.getenv("MILTON_STATE_DIR")
    if env_dir:
        # Expand both $VAR and ~ in the path
        return Path(os.path.expandvars(env_dir)).expanduser()
    return DEFAULT_STATE_DIR


def resolve_state_subdir(name: str, base_dir: Optional[Path] = None) -> Path:
    """Resolve a named subdirectory within the Milton state directory."""
    return resolve_state_dir(base_dir) / name


def resolve_reminders_db_path(base_dir: Optional[Path] = None, auto_migrate: bool = True) -> Path:
    """Resolve the canonical reminders database path.
    
    This is the ONLY function that should be used to determine the reminders
    database path. It ensures all components (API, scheduler, CLI) use the
    same database file.
    
    Resolution rules:
    1. If canonical reminders.db exists → use it
    2. Else if legacy reminders.sqlite3 exists → use it (log warning)
    3. If neither exists → use canonical reminders.db (create on first connect)
    4. If BOTH exist → merge legacy into canonical (one-time migration)
    
    Args:
        base_dir: Override state directory (defaults to resolve_state_dir())
        auto_migrate: If True, automatically merge DBs when both exist
        
    Returns:
        Path to the canonical reminders database file
    """
    state_dir = resolve_state_dir(base_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    
    canonical_path = state_dir / CANONICAL_REMINDERS_DB
    legacy_path = state_dir / LEGACY_REMINDERS_DB
    guard_file = state_dir / MIGRATION_GUARD_FILE
    
    canonical_exists = canonical_path.exists()
    legacy_exists = legacy_path.exists()
    
    # Case 1: Only canonical exists
    if canonical_exists and not legacy_exists:
        return canonical_path
    
    # Case 2: Only legacy exists
    if legacy_exists and not canonical_exists:
        logger.warning(
            f"Using legacy database path: {legacy_path}. "
            f"Will migrate to canonical path: {canonical_path}"
        )
        return legacy_path
    
    # Case 3: Neither exists
    if not canonical_exists and not legacy_exists:
        logger.info(f"No existing database found. Will create canonical: {canonical_path}")
        return canonical_path
    
    # Case 4: BOTH exist - SPLIT-BRAIN DETECTED!
    if canonical_exists and legacy_exists:
        # Check if migration already completed
        if guard_file.exists():
            logger.info(f"Migration already completed (guard file exists). Using canonical: {canonical_path}")
            return canonical_path
        
        logger.warning(
            f"⚠️  SPLIT-BRAIN DETECTED: Both {CANONICAL_REMINDERS_DB} and {LEGACY_REMINDERS_DB} exist!"
        )
        
        if auto_migrate:
            try:
                _merge_databases(canonical_path, legacy_path, state_dir)
                # Create guard file to prevent re-migration
                guard_file.write_text(
                    f"Migration completed at {datetime.now().isoformat()}\n"
                )
                logger.info(f"✓ Migration guard file created: {guard_file}")
            except Exception as e:
                logger.error(f"Failed to merge databases: {e}", exc_info=True)
                logger.warning(f"Falling back to canonical database: {canonical_path}")
        else:
            logger.warning(f"Auto-migration disabled. Using canonical: {canonical_path}")
        
        return canonical_path


def _merge_databases(canonical_path: Path, legacy_path: Path, state_dir: Path) -> None:
    """Merge legacy database into canonical database.
    
    Strategy:
    1. Open both databases
    2. Ensure schema is up-to-date on both
    3. Copy reminders from legacy that don't exist in canonical
    4. Backup legacy database after successful merge
    """
    logger.info(f"Starting database merge: {legacy_path} → {canonical_path}")
    
    # Open both databases
    canonical_conn = sqlite3.connect(canonical_path)
    legacy_conn = sqlite3.connect(legacy_path)
    
    canonical_conn.row_factory = sqlite3.Row
    legacy_conn.row_factory = sqlite3.Row
    
    try:
        # Get counts before merge
        canonical_count = canonical_conn.execute("SELECT COUNT(*) FROM reminders").fetchone()[0]
        legacy_count = legacy_conn.execute("SELECT COUNT(*) FROM reminders").fetchone()[0]
        
        logger.info(f"Pre-merge counts: canonical={canonical_count}, legacy={legacy_count}")
        
        if legacy_count == 0:
            logger.info("Legacy database is empty. No migration needed.")
            return
        
        # Get existing IDs in canonical to avoid conflicts
        existing_ids = {
            row[0] for row in canonical_conn.execute("SELECT id FROM reminders")
        }
        
        # Copy reminders from legacy to canonical
        legacy_reminders = legacy_conn.execute("SELECT * FROM reminders").fetchall()
        
        inserted = 0
        skipped = 0
        
        for row in legacy_reminders:
            row_dict = dict(row)
            reminder_id = row_dict["id"]
            
            if reminder_id in existing_ids:
                # ID conflict - check if it's the same reminder
                canonical_row = canonical_conn.execute(
                    "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
                ).fetchone()
                
                if canonical_row:
                    canonical_dict = dict(canonical_row)
                    # If message and due_at match, it's the same reminder - skip
                    if (canonical_dict.get("message") == row_dict.get("message") and
                        canonical_dict.get("due_at") == row_dict.get("due_at")):
                        skipped += 1
                        continue
                
                # ID conflict with different data - insert with new ID
                logger.warning(f"ID conflict for reminder {reminder_id}. Inserting with auto-generated ID.")
                # Remove the ID so SQLite auto-generates a new one
                columns = [k for k in row_dict.keys() if k != "id"]
            else:
                # No conflict - keep the ID
                columns = list(row_dict.keys())
            
            # Insert reminder
            placeholders = ", ".join(["?" for _ in columns])
            column_names = ", ".join(columns)
            values = [row_dict[col] for col in columns]
            
            canonical_conn.execute(
                f"INSERT INTO reminders ({column_names}) VALUES ({placeholders})",
                values
            )
            inserted += 1
            
            # Refresh existing IDs to avoid conflicts with auto-generated IDs
            existing_ids = {
                row[0] for row in canonical_conn.execute("SELECT id FROM reminders")
            }
        
        canonical_conn.commit()
        
        # Get counts after merge
        final_count = canonical_conn.execute("SELECT COUNT(*) FROM reminders").fetchone()[0]
        
        logger.info(
            f"✓ Database merge completed: "
            f"inserted={inserted}, skipped={skipped}, final_count={final_count}"
        )
        
        # Backup legacy database
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = state_dir / f"{LEGACY_REMINDERS_DB}.bak.{timestamp}"
        
        import shutil
        shutil.copy2(legacy_path, backup_path)
        logger.info(f"✓ Legacy database backed up to: {backup_path}")
        
    finally:
        canonical_conn.close()
        legacy_conn.close()


def parse_channels(channel_value: Optional[str]) -> list[str]:
    """Parse channel value from database into list of channel names.
    
    This function handles multiple formats for backward compatibility:
    - JSON list: '["ntfy"]' → ["ntfy"]
    - JSON list with multiple: '["ntfy","voice"]' → ["ntfy", "voice"]
    - Legacy "both": "both" → ["ntfy", "voice"]
    - Single string: "ntfy" → ["ntfy"]
    - Empty/None: None → ["ntfy"] (default)
    
    This prevents the ValueError crash when channel='["ntfy"]' is stored
    in the database as a JSON list string.
    
    Args:
        channel_value: Raw channel value from database (may be JSON or string)
        
    Returns:
        List of channel names (e.g., ["ntfy", "voice"])
    """
    if not channel_value:
        return ["ntfy"]
    
    # Try parsing as JSON list first
    try:
        parsed = json.loads(channel_value)
        if isinstance(parsed, list):
            # Validate all entries are strings
            channels = [str(c) for c in parsed if c]
            if not channels:
                return ["ntfy"]
            # Expand "both" if present
            expanded = []
            for ch in channels:
                if ch == "both":
                    expanded.extend(["ntfy", "voice"])
                else:
                    expanded.append(ch)
            # Remove duplicates while preserving order
            seen = set()
            result = []
            for ch in expanded:
                if ch not in seen:
                    seen.add(ch)
                    result.append(ch)
            return result
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    
    # Legacy single string
    channel_str = str(channel_value).strip()
    if channel_str == "both":
        return ["ntfy", "voice"]
    elif channel_str:
        return [channel_str]
    else:
        return ["ntfy"]
