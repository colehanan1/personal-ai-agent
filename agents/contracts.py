"""
Agent Message Contracts

This module defines the formal message contracts and schemas for inter-agent
communication in the Milton system. All agents (NEXUS, CORTEX, FRONTIER) must
use these contracts for their I/O to ensure testability and type safety.

Design principles:
- Explicit over implicit: all critical fields are required
- Evidence-backed: outputs include citations/evidence references
- Provenance: track task_id, created_at, requester for reproducibility
- Validation: strict validation with actionable error messages
- Single-user only: no multi-user isolation fields
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pathlib import Path


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Task priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AgentRole(Enum):
    """Agent role identifiers."""
    NEXUS = "nexus"
    CORTEX = "cortex"
    FRONTIER = "frontier"


# =============================================================================
# Core Message Contracts
# =============================================================================


@dataclass(frozen=True)
class TaskRequest:
    """
    Request for an agent to perform a task.

    Used by: NEXUS when routing to CORTEX/FRONTIER, external callers

    Fields:
        task_id: Unique task identifier (for tracking/correlation)
        created_at: ISO 8601 timestamp of request creation
        requester: Agent or system that created the request
        task_description: Human-readable task description
        priority: Task priority level
        context: Optional context dict (user preferences, constraints, etc.)
        evidence_refs: Optional evidence/citation IDs supporting the request
    """
    task_id: str
    created_at: str
    requester: str
    task_description: str
    priority: TaskPriority = TaskPriority.MEDIUM
    context: Dict[str, Any] = field(default_factory=dict)
    evidence_refs: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate required fields."""
        if not self.task_id or not self.task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        if not self.task_description or not self.task_description.strip():
            raise ValueError("task_description must be a non-empty string")
        if not self.requester or not self.requester.strip():
            raise ValueError("requester must be a non-empty string")

        # Validate ISO 8601 timestamp
        try:
            datetime.fromisoformat(self.created_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            raise ValueError(
                f"created_at must be valid ISO 8601 timestamp, got: {self.created_at}"
            )

        # Validate priority
        if not isinstance(self.priority, TaskPriority):
            raise ValueError(
                f"priority must be TaskPriority enum, got: {type(self.priority)}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict with enum serialization."""
        result = asdict(self)
        result["priority"] = self.priority.value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRequest":
        """Create from dict with enum deserialization."""
        copied = dict(data)
        if "priority" in copied and isinstance(copied["priority"], str):
            copied["priority"] = TaskPriority(copied["priority"])
        return cls(**copied)


@dataclass(frozen=True)
class TaskStep:
    """
    A single step in a task execution plan.

    Used by: CORTEX when breaking down tasks

    Fields:
        step_number: Step sequence number (1-indexed)
        action: Description of what to do in this step
        dependencies: List of step_numbers that must complete first
        estimated_complexity: low, medium, or high
        success_criteria: How to determine if step succeeded
    """
    step_number: int
    action: str
    dependencies: List[int] = field(default_factory=list)
    estimated_complexity: str = "medium"
    success_criteria: str = ""

    def __post_init__(self):
        """Validate step fields."""
        if self.step_number < 1:
            raise ValueError(f"step_number must be >= 1, got: {self.step_number}")
        if not self.action or not self.action.strip():
            raise ValueError("action must be a non-empty string")
        if self.estimated_complexity not in ("low", "medium", "high"):
            raise ValueError(
                f"estimated_complexity must be low/medium/high, got: {self.estimated_complexity}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskStep":
        """Create from dict."""
        return cls(**data)


@dataclass(frozen=True)
class TaskPlan:
    """
    Execution plan for a task.

    Used by: CORTEX when planning execution

    Fields:
        task_id: ID of the task being planned
        created_at: ISO 8601 timestamp of plan creation
        agent: Agent that created the plan
        steps: Ordered list of TaskStep objects
        overall_complexity: Overall complexity estimate
        required_tools: List of tool/integration names needed
        estimated_duration: Optional human-readable duration estimate
    """
    task_id: str
    created_at: str
    agent: str
    steps: List[TaskStep]
    overall_complexity: str = "medium"
    required_tools: List[str] = field(default_factory=list)
    estimated_duration: str = ""

    def __post_init__(self):
        """Validate plan fields."""
        if not self.task_id or not self.task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        if not self.agent or not self.agent.strip():
            raise ValueError("agent must be a non-empty string")
        if not self.steps:
            raise ValueError("steps must contain at least one TaskStep")

        # Validate all steps
        for i, step in enumerate(self.steps):
            if not isinstance(step, TaskStep):
                raise ValueError(f"steps[{i}] must be TaskStep, got: {type(step)}")

        # Validate ISO 8601 timestamp
        try:
            datetime.fromisoformat(self.created_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            raise ValueError(
                f"created_at must be valid ISO 8601 timestamp, got: {self.created_at}"
            )

        if self.overall_complexity not in ("low", "medium", "high"):
            raise ValueError(
                f"overall_complexity must be low/medium/high, got: {self.overall_complexity}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        result = asdict(self)
        result["steps"] = [step.to_dict() for step in self.steps]
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskPlan":
        """Create from dict."""
        if "steps" in data:
            data["steps"] = [TaskStep.from_dict(s) for s in data["steps"]]
        return cls(**data)


@dataclass(frozen=True)
class TaskResult:
    """
    Result of executing a task or task step.

    Used by: CORTEX after execution, FRONTIER after discovery

    Fields:
        task_id: ID of the task that was executed
        completed_at: ISO 8601 timestamp of completion
        agent: Agent that executed the task
        status: Final status (completed, failed, etc.)
        output: Primary output (text, code, data, etc.)
        output_paths: List of file paths where outputs were saved
        evidence_refs: Citations/references supporting the output
        error_message: Error details if status=failed
        metadata: Additional execution metadata
    """
    task_id: str
    completed_at: str
    agent: str
    status: TaskStatus
    output: str
    output_paths: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate result fields."""
        if not self.task_id or not self.task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        if not self.agent or not self.agent.strip():
            raise ValueError("agent must be a non-empty string")
        if not isinstance(self.status, TaskStatus):
            raise ValueError(
                f"status must be TaskStatus enum, got: {type(self.status)}"
            )

        # Validate ISO 8601 timestamp
        try:
            datetime.fromisoformat(self.completed_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            raise ValueError(
                f"completed_at must be valid ISO 8601 timestamp, got: {self.completed_at}"
            )

        # If failed, error_message should be provided
        if self.status == TaskStatus.FAILED and not self.error_message:
            raise ValueError("error_message must be provided when status=FAILED")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict with enum serialization."""
        result = asdict(self)
        result["status"] = self.status.value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResult":
        """Create from dict with enum deserialization."""
        if "status" in data and isinstance(data["status"], str):
            data["status"] = TaskStatus(data["status"])
        return cls(**data)


@dataclass(frozen=True)
class AgentReport:
    """
    Summary report from an agent (e.g., research brief, execution summary).

    Used by: All agents for high-level summaries

    Fields:
        report_id: Unique report identifier
        created_at: ISO 8601 timestamp of report creation
        agent: Agent that created the report
        report_type: Type of report (e.g., "research_brief", "execution_summary")
        summary: Human-readable summary text
        findings: List of key findings/results
        evidence_refs: Citations/references supporting findings
        output_paths: Paths to detailed output files
        metadata: Additional report metadata
    """
    report_id: str
    created_at: str
    agent: str
    report_type: str
    summary: str
    findings: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    output_paths: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate report fields."""
        if not self.report_id or not self.report_id.strip():
            raise ValueError("report_id must be a non-empty string")
        if not self.agent or not self.agent.strip():
            raise ValueError("agent must be a non-empty string")
        if not self.report_type or not self.report_type.strip():
            raise ValueError("report_type must be a non-empty string")
        if not self.summary or not self.summary.strip():
            raise ValueError("summary must be a non-empty string")

        # Validate ISO 8601 timestamp
        try:
            datetime.fromisoformat(self.created_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            raise ValueError(
                f"created_at must be valid ISO 8601 timestamp, got: {self.created_at}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentReport":
        """Create from dict."""
        return cls(**data)


# =============================================================================
# Discovery-Specific Contracts (FRONTIER)
# =============================================================================


@dataclass(frozen=True)
class DiscoveryResult:
    """
    Result of a research discovery task.

    Used by: FRONTIER for paper/news discovery

    Fields:
        task_id: ID of the discovery task
        completed_at: ISO 8601 timestamp
        agent: "frontier"
        query: Search query or topic
        summary: Brief summary of findings
        findings: Bullet-point list of key discoveries
        citations: arXiv IDs, URLs, DOIs, etc.
        source_timestamps: Timestamps for when each source was retrieved
        confidence: Confidence level (high/medium/low) or score (0.0-1.0)
        papers: List of discovered papers (with retrieved_at timestamps)
        news_items: List of discovered news items (with retrieved_at timestamps)
        output_path: Path to saved research brief
        metadata: Additional metadata (source counts, cache hits, etc.)
    """
    task_id: str
    completed_at: str
    agent: str
    query: str
    summary: str
    findings: List[str] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)
    source_timestamps: Dict[str, str] = field(default_factory=dict)
    confidence: str = "medium"
    papers: List[Dict[str, Any]] = field(default_factory=list)
    news_items: List[Dict[str, Any]] = field(default_factory=list)
    output_path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate discovery result."""
        if not self.task_id or not self.task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        if not self.agent or not self.agent.strip():
            raise ValueError("agent must be a non-empty string")
        if not self.query or not self.query.strip():
            raise ValueError("query must be a non-empty string")
        if not self.summary or not self.summary.strip():
            raise ValueError("summary must be a non-empty string")

        # Validate ISO 8601 timestamp
        try:
            datetime.fromisoformat(self.completed_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            raise ValueError(
                f"completed_at must be valid ISO 8601 timestamp, got: {self.completed_at}"
            )

        # Validate confidence
        if isinstance(self.confidence, str):
            valid_levels = ["low", "medium", "high"]
            if self.confidence.lower() not in valid_levels:
                raise ValueError(
                    f"confidence must be one of {valid_levels}, got: {self.confidence}"
                )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscoveryResult":
        """Create from dict."""
        return cls(**data)


# =============================================================================
# Utility Functions
# =============================================================================


def generate_task_id(prefix: str = "task") -> str:
    """
    Generate a unique task ID.

    Args:
        prefix: Prefix for the task ID

    Returns:
        Task ID in format: prefix_YYYYMMDD_HHMMSS_microseconds
    """
    now = datetime.now()
    return f"{prefix}_{now.strftime('%Y%m%d_%H%M%S')}_{now.microsecond}"


def generate_iso_timestamp() -> str:
    """
    Generate current timestamp in ISO 8601 format.

    Returns:
        ISO 8601 timestamp string
    """
    return datetime.now().isoformat()


def validate_contract(obj: Any) -> None:
    """
    Validate a contract object.

    This function relies on the __post_init__ validation in dataclasses.
    If the object was successfully created, it's valid.

    Args:
        obj: Contract object to validate

    Raises:
        ValueError: If validation fails
    """
    if not hasattr(obj, "__post_init__"):
        raise ValueError(f"Object {type(obj)} is not a contract dataclass")

    # Object validation happens in __post_init__, so if we got here, it's valid
    pass


def serialize_contract(obj: Any) -> str:
    """
    Serialize a contract object to JSON string.

    Args:
        obj: Contract object with to_dict() method

    Returns:
        JSON string
    """
    if not hasattr(obj, "to_dict"):
        raise ValueError(f"Object {type(obj)} must have to_dict() method")

    return json.dumps(obj.to_dict(), indent=2)


def deserialize_contract(cls: type, json_str: str) -> Any:
    """
    Deserialize JSON string to contract object.

    Args:
        cls: Contract class with from_dict() method
        json_str: JSON string

    Returns:
        Contract object instance
    """
    if not hasattr(cls, "from_dict"):
        raise ValueError(f"Class {cls} must have from_dict() method")

    data = json.loads(json_str)
    return cls.from_dict(data)


# =============================================================================
# Example Usage
# =============================================================================


if __name__ == "__main__":
    # Example: Create a task request
    request = TaskRequest(
        task_id=generate_task_id("cortex"),
        created_at=generate_iso_timestamp(),
        requester="nexus",
        task_description="Implement user authentication system",
        priority=TaskPriority.HIGH,
        context={"language": "python", "framework": "flask"},
        evidence_refs=["memory:req_001", "memory:pref_002"],
    )

    print("TaskRequest:")
    print(serialize_contract(request))
    print()

    # Example: Create a task plan
    plan = TaskPlan(
        task_id=request.task_id,
        created_at=generate_iso_timestamp(),
        agent="cortex",
        steps=[
            TaskStep(
                step_number=1,
                action="Design database schema for users and sessions",
                estimated_complexity="medium",
                success_criteria="Schema defined with all required fields",
            ),
            TaskStep(
                step_number=2,
                action="Implement password hashing and validation",
                dependencies=[1],
                estimated_complexity="low",
                success_criteria="Passwords properly hashed with bcrypt",
            ),
            TaskStep(
                step_number=3,
                action="Create login/logout endpoints",
                dependencies=[1, 2],
                estimated_complexity="medium",
                success_criteria="Endpoints return correct status codes",
            ),
        ],
        overall_complexity="medium",
        required_tools=["flask", "sqlalchemy", "bcrypt"],
    )

    print("TaskPlan:")
    print(serialize_contract(plan))
    print()

    # Example: Create a task result
    result = TaskResult(
        task_id=request.task_id,
        completed_at=generate_iso_timestamp(),
        agent="cortex",
        status=TaskStatus.COMPLETED,
        output="Authentication system implemented with Flask-Login",
        output_paths=[
            "milton/auth/models.py",
            "milton/auth/routes.py",
            "milton/auth/utils.py",
        ],
        evidence_refs=["test:auth_001", "test:auth_002"],
        metadata={"tests_passed": 12, "coverage": 0.95},
    )

    print("TaskResult:")
    print(serialize_contract(result))
    print()

    # Example: Create an agent report
    report = AgentReport(
        report_id=generate_task_id("report"),
        created_at=generate_iso_timestamp(),
        agent="frontier",
        report_type="research_brief",
        summary="Discovered 5 papers on fMRI brain connectivity",
        findings=[
            "New graph-based methods show 15% improvement",
            "Transfer learning from animal models is promising",
            "Multi-modal fusion techniques gaining traction",
        ],
        evidence_refs=[
            "arxiv:2401.12345",
            "arxiv:2401.23456",
            "arxiv:2401.34567",
        ],
        output_paths=["outputs/research_brief_20260102.txt"],
        metadata={"total_papers": 5, "categories": ["cs.LG", "q-bio.NC"]},
    )

    print("AgentReport:")
    print(serialize_contract(report))
