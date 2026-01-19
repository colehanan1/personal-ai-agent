# Daily OS Loop

Milton's daily operating loop captures goals, queues overnight jobs, and generates briefings.

**See also**: [RUNTIME.md](RUNTIME.md) for starting/stopping Milton services and smoke tests.

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

Queue jobs as JSON files in `STATE_DIR/job_queue/tonight/` (default: `~/.local/state/milton/job_queue/tonight/`) using `queue/api.py`:

```python
from milton_queue import enqueue_job

enqueue_job("cortex_task", {"task": "Summarize today's lab notes"}, priority="high")
```

Completed jobs move to `STATE_DIR/job_queue/archive/` with artifacts and results recorded.

## Queue Concurrency Check

Run the integration test to verify concurrent processors never drop or duplicate work:

```bash
pytest tests/test_queue_concurrency.py -q
```

This test enqueues 25 jobs rapidly, runs multiple worker processes against the queue, and asserts each job is processed exactly once with results archived.

## Queue Architecture Decision

Long-term queue architecture is the file-based queue API (`queue/api.py` via `milton_queue`) backed by `job_queue/{tonight,archive}`. The APScheduler-based `job_queue/job_manager.py` (and its SQLite `queue/jobs.db`) is considered legacy and should be treated as deprecated.

## Briefings

Evening briefing (capture + queue):

```bash
python scripts/evening_briefing.py
```

Morning briefing (weather + papers + overnight results + priorities):

```bash
python scripts/enhanced_morning_briefing.py
```

Both scripts write Markdown to `STATE_DIR/inbox/` (default: `~/.local/state/milton/inbox/`) and store a summary memory item with the briefing path as provenance.

### Verify Goals in Morning Briefing

Check current goals in state directory:

```bash
python -c "from goals.api import list_goals; import json; print(json.dumps(list_goals('daily'), indent=2))"
```

Generate morning briefing and verify goals section:

```bash
python scripts/enhanced_morning_briefing.py
# Find the generated file (default: ~/.local/state/milton/inbox/morning/YYYY-MM-DD.md)
rg -n "Goals" ~/.local/state/milton/inbox/morning/$(date +%Y-%m-%d)*.md
```

Run hermetic tests to verify goals integration:

```bash
pytest tests/test_morning_briefing_goals.py -v
```

## Systemd Timers (User)

Unit files live in `systemd/`. Install with:

```bash
bash scripts/systemd/install_daily_os.sh
```

Timers:
- Evening capture: 21:00
- Job processor: every 30 min from 22:00–06:00
- Morning briefing: 08:00

If your conda path differs, edit the unit files before installing.

## State Directory

`STATE_DIR` controls the base location for goals, queue, inbox, outputs, and logs.  
Default: `~/.local/state/milton`. Set `STATE_DIR` in `.env` (or your shell) to override (including repo-root paths for legacy layouts).
