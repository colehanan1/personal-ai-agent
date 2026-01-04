# Milton Agent System

This document describes the agent architecture, responsibilities, and message contracts for the Milton multi-agent system.

**Status**: Formalized as of 2026-01-02
**Scope**: Single-user deployment only (no multi-user isolation)

---

## Table of Contents

1. [Overview](#overview)
2. [Agent Roles and Boundaries](#agent-roles-and-boundaries)
3. [Message Contracts](#message-contracts)
4. [I/O Examples](#io-examples)
5. [Testing and Validation](#testing-and-validation)
6. [Integration Points](#integration-points)

---

## Overview

Milton uses three specialized agents that work together to handle user requests, execute tasks, and discover research:

- **NEXUS**: Orchestration hub (routing, briefings, tool dispatch)
- **CORTEX**: Execution agent (planning, task execution, overnight jobs)
- **FRONTIER**: Discovery agent (research papers, news monitoring, briefs)

All inter-agent communication uses **formal message contracts** defined in [agents/contracts.py](../agents/contracts.py). These contracts ensure:

- **Type safety**: All critical fields are validated
- **Provenance**: Every message includes task_id, created_at, requester
- **Evidence**: Outputs reference citations/sources
- **Testability**: Schemas can be validated independently

---

## Agent Roles and Boundaries

### NEXUS (Orchestration Hub)

**Location**: [agents/nexus.py](../agents/nexus.py)

**Responsibilities**:
- Route user requests to appropriate agents (CORTEX/FRONTIER) or tools
- Generate morning and evening briefings
- Handle direct user interactions (Q&A, simple lookups)
- Build evidence-backed context packets from memory
- Dispatch tools (weather, arXiv, reminders, web search)

**Inputs**:
- User messages (strings)
- Memory context (via `memory.retrieve.query_relevant`)
- Integration data (weather, calendar, news, home status)

**Outputs**:
- `Response` objects (text, citations, route_used, context_used)
- `RoutingDecision` objects (route, rationale, tool_name)
- Briefing text files saved to `STATE_DIR/inbox/`

**Key Methods**:
- `process_message(message: str) -> Response`: Main entry point
- `route_request(user_text: str) -> RoutingDecision`: Deterministic routing
- `build_context(user_text: str) -> ContextPacket`: Evidence-backed memory
- `generate_morning_briefing() -> str`: Daily AM briefing
- `generate_evening_briefing() -> str`: Daily PM briefing

**Contract Usage**:
- Imports `TaskRequest`, `TaskPriority`, `generate_task_id()` for delegation
- Uses internal `Response`, `ContextPacket`, `RoutingDecision` for own I/O

**Boundaries**:
- Does NOT execute multi-step tasks (delegates to CORTEX)
- Does NOT perform research discovery (delegates to FRONTIER)
- Does NOT run code or scripts (delegates to CORTEX)

---

### CORTEX (Execution Agent)

**Location**: [agents/cortex.py](../agents/cortex.py)

**Responsibilities**:
- Generate execution plans for multi-step tasks
- Execute task steps sequentially
- Write and run code (Python scripts)
- Process overnight jobs from the queue
- Generate execution reports

**Inputs**:
- `TaskRequest` objects (from NEXUS or queue)
- User task descriptions (strings, for backward compatibility)
- Job specifications (dicts with 'id' and 'task' fields)

**Outputs**:
- `TaskPlan` objects (task_id, steps, complexity, required_tools)
- `TaskResult` objects (task_id, status, output, evidence_refs, output_paths)
- Execution reports (text summaries)

**Key Methods**:
- `generate_plan(user_request: Union[str, TaskRequest]) -> TaskPlan`
- `execute_step(step: Dict, context: Dict) -> Dict`: Execute single step
- `process_overnight_job(job: Dict) -> TaskResult`: Process queued job
- `write_code(task: str, context: Dict) -> str`: Generate code
- `run_script(script_path: str, args: List) -> Dict`: Run Python script

**Contract Usage**:
- Consumes: `TaskRequest` (optional, for formal delegation)
- Produces: `TaskPlan`, `TaskResult` (required for critical paths)
- Legacy: Accepts plain strings and dicts for backward compatibility

**Boundaries**:
- Does NOT route requests (handled by NEXUS)
- Does NOT generate briefings (NEXUS responsibility)
- Does NOT discover research (FRONTIER responsibility)

---

### FRONTIER (Discovery Agent)

**Location**: [agents/frontier.py](../agents/frontier.py)

**Responsibilities**:
- Monitor arXiv for relevant papers
- Track AI/ML news developments
- Generate research briefs with citations
- Analyze paper relevance to user's research
- Curate content for research interests

**Inputs**:
- Research topics (strings)
- User's research interests (configurable list)
- Paper lists from arXiv API
- News items from NewsAPI

**Outputs**:
- `DiscoveryResult` objects (task_id, papers, news_items, citations, summary)
- `AgentReport` objects (for research briefs)
- Paper lists (dicts with title, authors, abstract, arxiv_id, pdf_url)
- Research brief text files saved to `STATE_DIR/outputs/`

**Key Methods**:
- `daily_discovery() -> DiscoveryResult`: Run daily discovery routine
- `find_papers(topic: str, max_results: int) -> List[Dict]`: Search arXiv
- `generate_research_brief(papers: List, topic: str) -> str`: Create brief
- `analyze_paper_relevance(paper: Dict) -> Dict`: LLM-based relevance scoring
- `monitor_ai_news(max_articles: int) -> List[Dict]`: Fetch AI news

**Contract Usage**:
- Produces: `DiscoveryResult` (for daily_discovery and major workflows)
- Produces: `AgentReport` (optional, for formal reporting)
- Legacy: Returns plain dicts/lists for paper searches

**Boundaries**:
- Does NOT execute tasks (CORTEX responsibility)
- Does NOT route requests (NEXUS responsibility)
- Does NOT generate system briefings (NEXUS responsibility)

---

## Message Contracts

All contracts are defined in [agents/contracts.py](../agents/contracts.py).

### TaskRequest

Request for an agent to perform a task.

**Required Fields**:
- `task_id: str` - Unique identifier (use `generate_task_id()`)
- `created_at: str` - ISO 8601 timestamp (use `generate_iso_timestamp()`)
- `requester: str` - Agent or system that created the request
- `task_description: str` - Human-readable task description
- `priority: TaskPriority` - LOW, MEDIUM, HIGH, URGENT

**Optional Fields**:
- `context: Dict[str, Any]` - Additional context (language, constraints, etc.)
- `evidence_refs: List[str]` - Memory IDs or citations supporting request

**Example**:
```python
from agents.contracts import TaskRequest, TaskPriority, generate_task_id, generate_iso_timestamp

request = TaskRequest(
    task_id=generate_task_id("cortex"),
    created_at=generate_iso_timestamp(),
    requester="nexus",
    task_description="Implement user authentication system",
    priority=TaskPriority.HIGH,
    context={"language": "python", "framework": "flask"},
    evidence_refs=["memory:req_001"],
)
```

---

### TaskPlan

Execution plan for a task (produced by CORTEX).

**Required Fields**:
- `task_id: str` - ID of the task being planned
- `created_at: str` - ISO 8601 timestamp
- `agent: str` - Agent that created the plan (e.g., "cortex")
- `steps: List[TaskStep]` - Ordered list of execution steps

**Optional Fields**:
- `overall_complexity: str` - "low", "medium", or "high"
- `required_tools: List[str]` - Tool/integration names needed
- `estimated_duration: str` - Human-readable duration estimate

**Example**:
```python
from agents.contracts import TaskPlan, TaskStep

plan = TaskPlan(
    task_id="cortex_20260102_143022_123456",
    created_at="2026-01-02T14:30:22",
    agent="cortex",
    steps=[
        TaskStep(
            step_number=1,
            action="Design database schema",
            estimated_complexity="medium",
            success_criteria="Schema includes all required fields",
        ),
        TaskStep(
            step_number=2,
            action="Implement password hashing",
            dependencies=[1],
            estimated_complexity="low",
            success_criteria="Passwords hashed with bcrypt",
        ),
    ],
    overall_complexity="medium",
    required_tools=["flask", "sqlalchemy", "bcrypt"],
)
```

---

### TaskResult

Result of executing a task (produced by CORTEX/FRONTIER).

**Required Fields**:
- `task_id: str` - ID of executed task
- `completed_at: str` - ISO 8601 timestamp
- `agent: str` - Agent that executed (e.g., "cortex")
- `status: TaskStatus` - PENDING, IN_PROGRESS, COMPLETED, FAILED, CANCELLED
- `output: str` - Primary output (text, code, summary)

**Optional Fields**:
- `output_paths: List[str]` - Paths to saved output files
- `evidence_refs: List[str]` - Citations/sources supporting output
- `error_message: str` - Error details if status=FAILED
- `metadata: Dict[str, Any]` - Additional execution metadata

**Example**:
```python
from agents.contracts import TaskResult, TaskStatus

result = TaskResult(
    task_id="cortex_20260102_143022_123456",
    completed_at="2026-01-02T14:45:00",
    agent="cortex",
    status=TaskStatus.COMPLETED,
    output="Authentication system implemented successfully",
    output_paths=["milton/auth/models.py", "milton/auth/routes.py"],
    evidence_refs=["test:auth_001", "test:auth_002"],
    metadata={"tests_passed": 12, "coverage": 0.95},
)
```

---

### DiscoveryResult

Result of a research discovery task (produced by FRONTIER).

**Required Fields**:
- `task_id: str` - Unique discovery task ID
- `completed_at: str` - ISO 8601 timestamp
- `agent: str` - "frontier"
- `query: str` - Search query or topic

**Optional Fields**:
- `papers: List[Dict]` - Discovered papers (arxiv format)
- `news_items: List[Dict]` - Discovered news articles
- `citations: List[str]` - arXiv IDs, URLs, etc.
- `summary: str` - Brief summary of findings
- `output_path: str` - Path to saved research brief

**Example**:
```python
from agents.contracts import DiscoveryResult

result = DiscoveryResult(
    task_id="discovery_20260102_080000",
    completed_at="2026-01-02T08:05:30",
    agent="frontier",
    query="Daily Discovery",
    papers=[
        {
            "title": "Graph Neural Networks for fMRI Analysis",
            "authors": ["Smith, J.", "Doe, A."],
            "arxiv_id": "2401.12345",
            "pdf_url": "https://arxiv.org/pdf/2401.12345.pdf",
        }
    ],
    citations=["arxiv:2401.12345"],
    summary="Discovered 5 papers on brain imaging and ML",
    output_path="outputs/research_brief_20260102.txt",
)
```

---

### AgentReport

High-level summary report from any agent.

**Required Fields**:
- `report_id: str` - Unique report identifier
- `created_at: str` - ISO 8601 timestamp
- `agent: str` - Agent that created report
- `report_type: str` - Type of report (e.g., "research_brief", "execution_summary")
- `summary: str` - Human-readable summary

**Optional Fields**:
- `findings: List[str]` - Key findings/results
- `evidence_refs: List[str]` - Citations supporting findings
- `output_paths: List[str]` - Paths to detailed output files
- `metadata: Dict[str, Any]` - Additional report metadata

**Example**:
```python
from agents.contracts import AgentReport

report = AgentReport(
    report_id="report_20260102_080000",
    created_at="2026-01-02T08:10:00",
    agent="frontier",
    report_type="research_brief",
    summary="Discovered 5 papers on fMRI brain connectivity",
    findings=[
        "New graph-based methods show 15% improvement",
        "Transfer learning from animal models is promising",
    ],
    evidence_refs=["arxiv:2401.12345", "arxiv:2401.23456"],
    output_paths=["outputs/research_brief_20260102.txt"],
)
```

---

## I/O Examples

### Example 1: NEXUS routes to CORTEX

```python
from agents.nexus import NEXUS
from agents.cortex import CORTEX
from agents.contracts import TaskRequest, TaskPriority, generate_task_id, generate_iso_timestamp

# User asks NEXUS to implement a feature
nexus = NEXUS()
response = nexus.process_message("Implement user authentication")

# NEXUS routes to CORTEX
if response.route_used == "cortex":
    # Create formal task request
    request = TaskRequest(
        task_id=generate_task_id("cortex"),
        created_at=generate_iso_timestamp(),
        requester="nexus",
        task_description="Implement user authentication",
        priority=TaskPriority.HIGH,
    )

    # CORTEX generates plan
    cortex = CORTEX()
    plan = cortex.generate_plan(request)

    # Inspect plan
    print(f"Task: {plan.task_id}")
    print(f"Steps: {len(plan.steps)}")
    for step in plan.steps:
        print(f"  {step.step_number}. {step.action}")
```

### Example 2: CORTEX processes overnight job

```python
from agents.cortex import CORTEX
from agents.contracts import TaskStatus

cortex = CORTEX()

# Job from queue
job = {
    "id": "job_001",
    "task": "Analyze logs and generate performance report",
}

# Process job (returns TaskResult)
result = cortex.process_overnight_job(job)

# Inspect result
print(f"Status: {result.status.value}")
print(f"Output: {result.output}")
print(f"Metadata: {result.metadata}")

# Check for errors
if result.status == TaskStatus.FAILED:
    print(f"Error: {result.error_message}")
```

### Example 3: FRONTIER daily discovery

```python
from agents.frontier import FRONTIER

frontier = FRONTIER()

# Run daily discovery
result = frontier.daily_discovery()

# Inspect result
print(f"Query: {result.query}")
print(f"Papers found: {len(result.papers)}")
print(f"News items: {len(result.news_items)}")
print(f"Citations: {result.citations}")
print(f"Summary: {result.summary}")

# Access papers
for paper in result.papers[:3]:
    print(f"  - {paper['title']}")
```

---

## Testing and Validation

### Contract Validation

All contract objects validate their fields in `__post_init__`. Invalid objects raise `ValueError` with actionable messages.

```python
from agents.contracts import TaskRequest, TaskPriority, generate_task_id, generate_iso_timestamp

# Valid request
request = TaskRequest(
    task_id=generate_task_id("test"),
    created_at=generate_iso_timestamp(),
    requester="test",
    task_description="Test task",
    priority=TaskPriority.MEDIUM,
)

# Invalid request (empty task_id)
try:
    bad_request = TaskRequest(
        task_id="",  # Invalid!
        created_at=generate_iso_timestamp(),
        requester="test",
        task_description="Test task",
        priority=TaskPriority.MEDIUM,
    )
except ValueError as e:
    print(f"Validation error: {e}")
    # Output: "task_id must be a non-empty string"
```

### Unit Tests

See [tests/test_agent_contracts.py](../tests/test_agent_contracts.py) for comprehensive unit tests covering:

- Contract validation (required fields, timestamps, enums)
- Serialization/deserialization (to_dict, from_dict, JSON)
- Agent method signatures (CORTEX.generate_plan, FRONTIER.daily_discovery)
- Error handling (invalid inputs, failed tasks)

Run tests with:
```bash
pytest tests/test_agent_contracts.py -v
```

---

## Integration Points

### Queue System

The overnight job processor ([scripts/job_processor.py](../scripts/job_processor.py)) reads jobs from `STATE_DIR/job_queue/tonight/` and calls:

```python
cortex = CORTEX()
result = cortex.process_overnight_job(job)
```

Job files are JSON dicts with `id` and `task` fields. The processor should handle both `TaskResult` objects and legacy dict returns.

### API Server

The Flask API server ([scripts/start_api_server.py](../scripts/start_api_server.py)) exposes endpoints for all three agents. It should:

- Accept `TaskRequest` JSON payloads (or plain strings for backward compat)
- Return `TaskPlan`, `TaskResult`, `DiscoveryResult` as JSON
- Serialize enums as strings (`.value`)

Example endpoint:
```python
@app.route("/api/cortex/plan", methods=["POST"])
def cortex_plan():
    data = request.json
    cortex = CORTEX()

    # Accept both TaskRequest and plain string
    if isinstance(data, dict) and "task_description" in data:
        task_request = TaskRequest.from_dict(data)
        plan = cortex.generate_plan(task_request)
    else:
        plan = cortex.generate_plan(data.get("task", ""))

    return jsonify(plan.to_dict())
```

### Dashboard

The React dashboard ([milton-dashboard/](../milton-dashboard/)) should:

- Send `TaskRequest` JSON to API endpoints
- Parse `TaskPlan`, `TaskResult`, `DiscoveryResult` responses
- Display status enums as human-readable strings
- Render evidence_refs as clickable citations

### Memory System

Agents record memory via [agents/memory_hooks.py](../agents/memory_hooks.py). Memory items can reference task_ids and evidence_refs from contracts:

```python
record_memory(
    agent="cortex",
    content=f"Completed task {result.task_id}",
    memory_type="result",
    tags=["execution", "completed"],
    importance=0.3,
    metadata={"task_id": result.task_id, "status": result.status.value},
)
```

---

## Migration Notes

### Backward Compatibility

- **CORTEX.generate_plan()**: Accepts both `TaskRequest` objects and plain strings
- **CORTEX.process_overnight_job()**: Accepts dict jobs, returns `TaskResult`
- **FRONTIER.daily_discovery()**: Returns `DiscoveryResult` instead of dict
- **NEXUS**: Unchanged, already uses well-defined internal contracts

### Deprecation Path

Legacy dict-based returns will continue to work but should be migrated to contract types:
Legacy return types remain supported only for backward compatibility; new code should use the contract types above.

| Method | Legacy Return | New Return | Deadline |
|--------|---------------|------------|----------|
| `CORTEX.generate_plan()` | `Dict[str, Any]` | `TaskPlan` | Migration complete (legacy retained for backward compatibility) |
| `CORTEX.process_overnight_job()` | `Dict[str, Any]` | `TaskResult` | Migration complete (legacy retained for backward compatibility) |
| `FRONTIER.daily_discovery()` | `Dict[str, Any]` | `DiscoveryResult` | Migration complete (legacy retained for backward compatibility) |

### Testing Requirements

All new code must:
1. Use contract types for critical paths (job processing, discovery, delegation)
2. Include unit tests that validate contract behavior
3. Handle both old and new formats during transition (backward compat)

---

## References

- [agents/contracts.py](../agents/contracts.py) - Contract definitions and validation
- [agents/nexus.py](../agents/nexus.py) - NEXUS implementation
- [agents/cortex.py](../agents/cortex.py) - CORTEX implementation
- [agents/frontier.py](../agents/frontier.py) - FRONTIER implementation
- [tests/test_agent_contracts.py](../tests/test_agent_contracts.py) - Contract unit tests
- [MILTON_SYSTEM_SUMMARY.md](MILTON_SYSTEM_SUMMARY.md) - Overall system documentation

---

**Last Updated**: 2026-01-02
**Maintainer**: Cole Hanan
**Status**: Formalized, testable, single-user only
