"""
Unit tests for agent message contracts.

This module tests:
1. Contract validation (required fields, types, timestamps)
2. Serialization/deserialization (to_dict, from_dict, JSON)
3. Agent method signatures (generate_plan, daily_discovery, etc.)
4. Error handling and actionable error messages
"""

import json
import pytest
from datetime import datetime

from agents.contracts import (
    TaskRequest,
    TaskPlan,
    TaskStep,
    TaskResult,
    TaskStatus,
    TaskPriority,
    AgentRole,
    AgentReport,
    DiscoveryResult,
    generate_task_id,
    generate_iso_timestamp,
    validate_contract,
    serialize_contract,
    deserialize_contract,
)


# =============================================================================
# Test Utility Functions
# =============================================================================


def test_generate_task_id():
    """Test task ID generation."""
    task_id = generate_task_id("test")
    assert task_id.startswith("test_")
    assert len(task_id) > 10  # Should include timestamp

    # IDs should be unique
    id1 = generate_task_id("test")
    id2 = generate_task_id("test")
    assert id1 != id2


def test_generate_iso_timestamp():
    """Test ISO 8601 timestamp generation."""
    ts = generate_iso_timestamp()
    # Should be parseable as ISO 8601
    parsed = datetime.fromisoformat(ts)
    assert isinstance(parsed, datetime)


# =============================================================================
# Test TaskRequest
# =============================================================================


def test_task_request_valid():
    """Test valid TaskRequest creation."""
    request = TaskRequest(
        task_id="test_001",
        created_at=generate_iso_timestamp(),
        requester="nexus",
        task_description="Test task",
        priority=TaskPriority.MEDIUM,
        context={"key": "value"},
        evidence_refs=["mem_001"],
    )

    assert request.task_id == "test_001"
    assert request.requester == "nexus"
    assert request.task_description == "Test task"
    assert request.priority == TaskPriority.MEDIUM
    assert request.context == {"key": "value"}
    assert request.evidence_refs == ["mem_001"]


def test_task_request_empty_task_id():
    """Test TaskRequest validation: empty task_id."""
    with pytest.raises(ValueError, match="task_id must be a non-empty string"):
        TaskRequest(
            task_id="",
            created_at=generate_iso_timestamp(),
            requester="nexus",
            task_description="Test task",
        )


def test_task_request_empty_description():
    """Test TaskRequest validation: empty task_description."""
    with pytest.raises(ValueError, match="task_description must be a non-empty string"):
        TaskRequest(
            task_id="test_001",
            created_at=generate_iso_timestamp(),
            requester="nexus",
            task_description="",
        )


def test_task_request_invalid_timestamp():
    """Test TaskRequest validation: invalid timestamp."""
    with pytest.raises(ValueError, match="created_at must be valid ISO 8601 timestamp"):
        TaskRequest(
            task_id="test_001",
            created_at="not a timestamp",
            requester="nexus",
            task_description="Test task",
        )


def test_task_request_serialization():
    """Test TaskRequest to_dict and from_dict."""
    request = TaskRequest(
        task_id="test_001",
        created_at="2026-01-02T10:00:00",
        requester="nexus",
        task_description="Test task",
        priority=TaskPriority.HIGH,
    )

    # Serialize
    data = request.to_dict()
    assert data["task_id"] == "test_001"
    assert data["priority"] == "high"  # Enum serialized as string

    # Deserialize
    restored = TaskRequest.from_dict(data)
    assert restored.task_id == request.task_id
    assert restored.priority == TaskPriority.HIGH  # Enum restored


# =============================================================================
# Test TaskStep
# =============================================================================


def test_task_step_valid():
    """Test valid TaskStep creation."""
    step = TaskStep(
        step_number=1,
        action="Do something",
        dependencies=[],
        estimated_complexity="medium",
        success_criteria="Task completed",
    )

    assert step.step_number == 1
    assert step.action == "Do something"
    assert step.estimated_complexity == "medium"


def test_task_step_invalid_step_number():
    """Test TaskStep validation: step_number < 1."""
    with pytest.raises(ValueError, match="step_number must be >= 1"):
        TaskStep(
            step_number=0,
            action="Do something",
        )


def test_task_step_invalid_complexity():
    """Test TaskStep validation: invalid complexity."""
    with pytest.raises(ValueError, match="estimated_complexity must be low/medium/high"):
        TaskStep(
            step_number=1,
            action="Do something",
            estimated_complexity="extreme",
        )


def test_task_step_serialization():
    """Test TaskStep to_dict and from_dict."""
    step = TaskStep(
        step_number=1,
        action="Do something",
        dependencies=[],
        estimated_complexity="high",
    )

    data = step.to_dict()
    restored = TaskStep.from_dict(data)

    assert restored.step_number == step.step_number
    assert restored.action == step.action
    assert restored.estimated_complexity == step.estimated_complexity


# =============================================================================
# Test TaskPlan
# =============================================================================


def test_task_plan_valid():
    """Test valid TaskPlan creation."""
    steps = [
        TaskStep(step_number=1, action="Step 1"),
        TaskStep(step_number=2, action="Step 2", dependencies=[1]),
    ]

    plan = TaskPlan(
        task_id="test_001",
        created_at=generate_iso_timestamp(),
        agent="cortex",
        steps=steps,
        overall_complexity="medium",
        required_tools=["tool1", "tool2"],
    )

    assert plan.task_id == "test_001"
    assert plan.agent == "cortex"
    assert len(plan.steps) == 2
    assert plan.overall_complexity == "medium"


def test_task_plan_empty_steps():
    """Test TaskPlan validation: empty steps."""
    with pytest.raises(ValueError, match="steps must contain at least one TaskStep"):
        TaskPlan(
            task_id="test_001",
            created_at=generate_iso_timestamp(),
            agent="cortex",
            steps=[],
        )


def test_task_plan_invalid_step_type():
    """Test TaskPlan validation: invalid step type."""
    with pytest.raises(ValueError, match="must be TaskStep"):
        TaskPlan(
            task_id="test_001",
            created_at=generate_iso_timestamp(),
            agent="cortex",
            steps=["not a TaskStep"],  # Invalid!
        )


def test_task_plan_serialization():
    """Test TaskPlan to_dict and from_dict."""
    plan = TaskPlan(
        task_id="test_001",
        created_at="2026-01-02T10:00:00",
        agent="cortex",
        steps=[
            TaskStep(step_number=1, action="Step 1"),
        ],
        overall_complexity="low",
    )

    data = plan.to_dict()
    assert data["task_id"] == "test_001"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["action"] == "Step 1"

    restored = TaskPlan.from_dict(data)
    assert restored.task_id == plan.task_id
    assert len(restored.steps) == 1
    assert restored.steps[0].action == "Step 1"


# =============================================================================
# Test TaskResult
# =============================================================================


def test_task_result_completed():
    """Test valid TaskResult with COMPLETED status."""
    result = TaskResult(
        task_id="test_001",
        completed_at=generate_iso_timestamp(),
        agent="cortex",
        status=TaskStatus.COMPLETED,
        output="Task completed successfully",
        output_paths=["output.txt"],
        evidence_refs=["test_001"],
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.output == "Task completed successfully"
    assert len(result.output_paths) == 1


def test_task_result_failed_without_error():
    """Test TaskResult validation: FAILED without error_message."""
    with pytest.raises(ValueError, match="error_message must be provided when status=FAILED"):
        TaskResult(
            task_id="test_001",
            completed_at=generate_iso_timestamp(),
            agent="cortex",
            status=TaskStatus.FAILED,
            output="",
            error_message="",  # Invalid!
        )


def test_task_result_failed_with_error():
    """Test valid TaskResult with FAILED status and error_message."""
    result = TaskResult(
        task_id="test_001",
        completed_at=generate_iso_timestamp(),
        agent="cortex",
        status=TaskStatus.FAILED,
        output="",
        error_message="Task failed due to missing dependency",
    )

    assert result.status == TaskStatus.FAILED
    assert "missing dependency" in result.error_message


def test_task_result_serialization():
    """Test TaskResult to_dict and from_dict."""
    result = TaskResult(
        task_id="test_001",
        completed_at="2026-01-02T10:00:00",
        agent="cortex",
        status=TaskStatus.COMPLETED,
        output="Done",
    )

    data = result.to_dict()
    assert data["status"] == "completed"  # Enum as string

    restored = TaskResult.from_dict(data)
    assert restored.status == TaskStatus.COMPLETED  # Enum restored


# =============================================================================
# Test AgentReport
# =============================================================================


def test_agent_report_valid():
    """Test valid AgentReport creation."""
    report = AgentReport(
        report_id="report_001",
        created_at=generate_iso_timestamp(),
        agent="frontier",
        report_type="research_brief",
        summary="Found 5 papers on brain imaging",
        findings=["Finding 1", "Finding 2"],
        evidence_refs=["arxiv:2401.12345"],
        output_paths=["brief.txt"],
    )

    assert report.report_type == "research_brief"
    assert len(report.findings) == 2
    assert len(report.evidence_refs) == 1


def test_agent_report_empty_summary():
    """Test AgentReport validation: empty summary."""
    with pytest.raises(ValueError, match="summary must be a non-empty string"):
        AgentReport(
            report_id="report_001",
            created_at=generate_iso_timestamp(),
            agent="frontier",
            report_type="research_brief",
            summary="",  # Invalid!
        )


def test_agent_report_serialization():
    """Test AgentReport to_dict and from_dict."""
    report = AgentReport(
        report_id="report_001",
        created_at="2026-01-02T10:00:00",
        agent="frontier",
        report_type="research_brief",
        summary="Test summary",
    )

    data = report.to_dict()
    restored = AgentReport.from_dict(data)

    assert restored.report_id == report.report_id
    assert restored.summary == report.summary


# =============================================================================
# Test DiscoveryResult
# =============================================================================


def test_discovery_result_valid():
    """Test valid DiscoveryResult creation."""
    result = DiscoveryResult(
        task_id="discovery_001",
        completed_at=generate_iso_timestamp(),
        agent="frontier",
        query="fMRI brain imaging",
        papers=[{"title": "Paper 1"}],
        citations=["arxiv:2401.12345"],
        summary="Found 1 paper",
    )

    assert result.query == "fMRI brain imaging"
    assert len(result.papers) == 1
    assert len(result.citations) == 1


def test_discovery_result_empty_query():
    """Test DiscoveryResult validation: empty query."""
    with pytest.raises(ValueError, match="query must be a non-empty string"):
        DiscoveryResult(
            task_id="discovery_001",
            completed_at=generate_iso_timestamp(),
            agent="frontier",
            query="",  # Invalid!
            summary="Test summary",
        )


def test_discovery_result_serialization():
    """Test DiscoveryResult to_dict and from_dict."""
    result = DiscoveryResult(
        task_id="discovery_001",
        completed_at="2026-01-02T10:00:00",
        agent="frontier",
        query="test query",
        summary="Test discovery summary",
        findings=["Finding 1", "Finding 2"],
        citations=["arxiv:2401.12345"],
        confidence="high",
        papers=[{"title": "Test"}],
    )

    data = result.to_dict()
    restored = DiscoveryResult.from_dict(data)

    assert restored.task_id == result.task_id
    assert restored.query == result.query
    assert len(restored.papers) == 1


# =============================================================================
# Test JSON Serialization Helpers
# =============================================================================


def test_serialize_contract():
    """Test serialize_contract helper."""
    request = TaskRequest(
        task_id="test_001",
        created_at="2026-01-02T10:00:00",
        requester="nexus",
        task_description="Test",
    )

    json_str = serialize_contract(request)
    data = json.loads(json_str)

    assert data["task_id"] == "test_001"
    assert data["requester"] == "nexus"


def test_deserialize_contract():
    """Test deserialize_contract helper."""
    json_str = json.dumps({
        "task_id": "test_001",
        "created_at": "2026-01-02T10:00:00",
        "requester": "nexus",
        "task_description": "Test",
        "priority": "medium",
        "context": {},
        "evidence_refs": [],
    })

    request = deserialize_contract(TaskRequest, json_str)

    assert isinstance(request, TaskRequest)
    assert request.task_id == "test_001"
    assert request.priority == TaskPriority.MEDIUM


def test_validate_contract():
    """Test validate_contract helper."""
    # Valid contract
    request = TaskRequest(
        task_id="test_001",
        created_at=generate_iso_timestamp(),
        requester="nexus",
        task_description="Test",
    )

    # Should not raise
    validate_contract(request)

    # Invalid object
    with pytest.raises(ValueError):
        validate_contract("not a contract")


# =============================================================================
# Test Agent Integration (Minimal Mocks)
# =============================================================================


@pytest.mark.integration(reason="CORTEX initialization is slow; opt-in only.")
def test_cortex_generate_plan_returns_task_plan():
    """Test that CORTEX.generate_plan returns TaskPlan."""
    # Note: This is a signature test, not a full integration test
    # We're just ensuring the return type is correct

    from agents.cortex import CORTEX
    from unittest.mock import MagicMock

    cortex = CORTEX()

    # Mock the LLM call to avoid actual API calls
    cortex._call_llm = MagicMock(return_value=json.dumps({
        "steps": [
            {
                "step_number": 1,
                "action": "Test step",
                "dependencies": [],
                "estimated_complexity": "low",
                "success_criteria": "Done",
            }
        ],
        "overall_complexity": "low",
        "required_tools": [],
    }))

    plan = cortex.generate_plan("Test task")

    assert isinstance(plan, TaskPlan)
    assert plan.agent == "cortex"
    assert len(plan.steps) > 0
    assert isinstance(plan.steps[0], TaskStep)


@pytest.mark.integration(reason="CORTEX job processing is slow; opt-in only.")
def test_cortex_process_overnight_job_returns_task_result():
    """Test that CORTEX.process_overnight_job returns TaskResult."""
    from agents.cortex import CORTEX
    from unittest.mock import MagicMock

    cortex = CORTEX()

    # Mock LLM calls
    cortex._call_llm = MagicMock(side_effect=[
        # First call: generate_plan
        json.dumps({
            "steps": [{"step_number": 1, "action": "Test", "dependencies": []}],
            "overall_complexity": "low",
        }),
        # Second call: execute_step
        "Step completed",
        # Third call: generate_report
        "Report generated",
    ])

    job = {"id": "job_001", "task": "Test job"}
    result = cortex.process_overnight_job(job)

    assert isinstance(result, TaskResult)
    assert result.task_id == "job_001"
    assert result.agent == "cortex"
    assert result.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)


@pytest.mark.integration(reason="FRONTIER agent setup is slow; opt-in only.")
def test_frontier_daily_discovery_returns_discovery_result(tmp_path, monkeypatch):
    """Test that FRONTIER.daily_discovery returns DiscoveryResult."""
    from agents.frontier import FRONTIER
    from agents.frontier_cache import DiscoveryCache
    import agents.frontier_cache as frontier_cache
    from unittest.mock import MagicMock

    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.setattr(
        frontier_cache,
        "_global_cache",
        DiscoveryCache(cache_dir=tmp_path / "cache" / "frontier"),
    )

    frontier = FRONTIER()

    # Mock arXiv and news APIs
    frontier.arxiv.search_papers = MagicMock(return_value=[
        {
            "title": "Test Paper",
            "authors": ["Smith, J."],
            "arxiv_id": "2401.12345",
            "pdf_url": "https://arxiv.org/pdf/2401.12345.pdf",
            "abstract": "Test abstract",
            "published": "2026-01-01",
            "id": "2401.12345",
        }
    ])

    frontier.news.get_recent_news = MagicMock(return_value=[])

    # Mock LLM call for brief generation
    frontier._call_llm = MagicMock(return_value="Research brief summary")

    result = frontier.daily_discovery()

    assert isinstance(result, DiscoveryResult)
    assert result.agent == "frontier"
    assert result.query == "Daily Discovery"
    assert len(result.papers) > 0
    assert len(result.citations) > 0


# =============================================================================
# Test Backward Compatibility
# =============================================================================


@pytest.mark.integration(reason="CORTEX initialization is slow; opt-in only.")
def test_cortex_generate_plan_accepts_string():
    """Test that CORTEX.generate_plan still accepts plain strings."""
    from agents.cortex import CORTEX
    from unittest.mock import MagicMock

    cortex = CORTEX()
    cortex._call_llm = MagicMock(return_value=json.dumps({
        "steps": [{"step_number": 1, "action": "Test"}],
    }))

    # Should accept plain string
    plan = cortex.generate_plan("Test task string")

    assert isinstance(plan, TaskPlan)


@pytest.mark.integration(reason="CORTEX initialization is slow; opt-in only.")
def test_cortex_generate_plan_accepts_task_request():
    """Test that CORTEX.generate_plan accepts TaskRequest."""
    from agents.cortex import CORTEX
    from unittest.mock import MagicMock

    cortex = CORTEX()
    cortex._call_llm = MagicMock(return_value=json.dumps({
        "steps": [{"step_number": 1, "action": "Test"}],
    }))

    request = TaskRequest(
        task_id="test_001",
        created_at=generate_iso_timestamp(),
        requester="nexus",
        task_description="Test task",
    )

    plan = cortex.generate_plan(request)

    assert isinstance(plan, TaskPlan)
    assert plan.task_id == "test_001"  # Should use request's task_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
