# Architecture Namespace Conventions

This repository uses a single canonical namespace and pathing strategy to avoid
import and path drift.

## Canonical Naming

- Repository root directory: `milton`
- Python packages:
  - `milton_orchestrator` (core runtime + CLI)
  - `agents`, `integrations`, `memory`, `job_queue` (domain modules)

## Pathing Strategy

- Use repo-relative paths when referring to project files.
- Prefer `Path(__file__).resolve().parents[1]` to locate the repo root.
- Avoid hardcoded references to `agent-system` or `agent_system`.

## Data Locations

- Runtime state (default): `~/.local/state/milton` (override with `STATE_DIR`)
- Repo data folders (`inbox/`, `output/`, `outputs/`, `logs/`) are legacy/optional; use symlinks or set `STATE_DIR` to keep repo-root paths.

### Default State Layout

```
~/.local/state/milton/
|-- inbox/
|   |-- morning/
|   `-- evening/
|-- job_queue/
|   |-- tonight/
|   `-- archive/
|-- outputs/
|-- logs/
|-- queue/
|   `-- jobs.db
|-- reminders.sqlite3
`-- data/
    `-- memory/
```
