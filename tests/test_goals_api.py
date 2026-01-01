from datetime import datetime, timezone
import yaml

from goals import api as goals_api


def test_add_and_list_goals(tmp_path):
    now = datetime(2025, 1, 2, 9, 0, tzinfo=timezone.utc)
    goal_id = goals_api.add_goal(
        "daily",
        "Review experiment notes",
        tags=["Research", "Review"],
        base_dir=tmp_path,
        now=now,
    )

    goals = goals_api.list_goals("daily", base_dir=tmp_path)
    assert len(goals) == 1
    assert goals[0]["id"] == goal_id
    assert goals[0]["status"] == "active"
    assert goals[0]["tags"] == ["research", "review"]


def test_complete_goal_moves_to_archive(tmp_path):
    now = datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc)
    goal_id = goals_api.add_goal(
        "daily",
        "Finish draft",
        base_dir=tmp_path,
        now=now,
    )

    completed = goals_api.complete_goal("daily", goal_id, base_dir=tmp_path, now=now)
    assert completed["status"] == "completed"

    assert goals_api.list_goals("daily", base_dir=tmp_path) == []

    archive_path = tmp_path / "goals" / "archive" / "daily.yaml"
    archive_data = yaml.safe_load(archive_path.read_text())
    archived_ids = [goal["id"] for goal in archive_data.get("goals", [])]
    assert goal_id in archived_ids


def test_defer_goal_moves_scope(tmp_path):
    now = datetime(2025, 1, 2, 11, 0, tzinfo=timezone.utc)
    goal_id = goals_api.add_goal(
        "daily",
        "Prep weekly summary",
        base_dir=tmp_path,
        now=now,
    )

    deferred = goals_api.defer_goal("daily", goal_id, new_scope="weekly", base_dir=tmp_path, now=now)
    assert deferred["deferred_from"] == "daily"

    assert goals_api.list_goals("daily", base_dir=tmp_path) == []
    weekly_goals = goals_api.list_goals("weekly", base_dir=tmp_path)
    assert weekly_goals[0]["id"] == goal_id
