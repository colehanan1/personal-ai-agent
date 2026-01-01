# Daily OS Loop

Milton's daily operating loop captures goals, queues overnight jobs, and generates briefings.

## Goals

Goals live in `goals/current/{daily,weekly,monthly}.yaml` and are managed via `goals/api.py`:

```python
from goals.api import add_goal, list_goals, complete_goal, defer_goal

add_goal("daily", "Draft project summary", tags=["writing"])  # returns goal id
list_goals("daily")
complete_goal("daily", "d-20250101-001")
defer_goal("daily", "d-20250101-002", new_scope="weekly")
```

## Overnight Queue

Queue jobs as JSON files in `job_queue/tonight/` using `queue/api.py`:

```python
from milton_queue import enqueue_job

enqueue_job("cortex_task", {"task": "Summarize today's lab notes"}, priority="high")
```

Completed jobs move to `job_queue/archive/` with artifacts and results recorded.

## Briefings

Evening briefing (capture + queue):

```bash
python scripts/evening_briefing.py
```

Morning briefing (weather + papers + overnight results + priorities):

```bash
python scripts/enhanced_morning_briefing.py
```

Both scripts write Markdown to `inbox/` and store a summary memory item with the briefing path as provenance.

## Systemd Timers (User)

Unit files live in `scripts/systemd/`. Install with:

```bash
bash scripts/systemd/install_daily_os.sh
```

Timers:
- Evening capture: 21:00
- Job processor: every 30 min from 22:00–06:00
- Morning briefing: 08:00

If your conda path differs, edit the unit files before installing.

## State Directory

Set `STATE_DIR` in `.env` (or your shell) to write goals/queue/inbox outside the repo root.
