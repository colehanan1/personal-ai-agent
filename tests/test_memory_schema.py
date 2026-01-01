import pytest
from pydantic import ValidationError

from memory.schema import MemoryItem, ProjectMemory, UserProfile


def test_memory_item_validation_errors():
    with pytest.raises(ValidationError):
        MemoryItem(agent="NEXUS", type="unknown", content="x", source="chat")

    with pytest.raises(ValidationError):
        MemoryItem(
            agent="NEXUS",
            type="fact",
            content="x",
            source="chat",
            importance=1.5,
        )


def test_memory_item_tag_normalization():
    item = MemoryItem(
        agent="NEXUS",
        type="fact",
        content="Test",
        source="chat",
        tags=["Alpha", "alpha", " ", "Beta"],
        evidence=["File.txt", "file.txt", " "],
    )
    assert item.tags == ["alpha", "beta"]
    assert item.evidence == ["File.txt", "file.txt"]


def test_profile_and_project_validation():
    profile = UserProfile(preferences=["fast"], stable_facts=["x"], do_not_assume=[])
    assert profile.preferences == ["fast"]

    project = ProjectMemory(
        project_name="milton",
        goals=["ship"],
        blockers=["none"],
        next_steps=["test"],
        evidence_ids=["id-1"],
    )
    assert project.project_name == "milton"
