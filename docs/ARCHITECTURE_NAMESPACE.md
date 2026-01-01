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

- Runtime state: `~/.local/state/milton_orchestrator`
- Repo data folders: `inbox/`, `outputs/`, `logs/`
