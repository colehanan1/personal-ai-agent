# Self-Upgrade Capability

## Overview

Milton now supports **supervised self-upgrade**: a branch-based workflow that allows the agent to propose, implement, and test code changes while maintaining strict security guardrails.

## Key Features

- ✅ **Branch-Based Workflow**: All changes occur in isolated `self-upgrade/<topic>` branches
- ✅ **Policy Enforcement**: Prevents edits to secrets, protected branches, deployment configs
- ✅ **Safe Command Execution**: Commands are validated, logged, and timeout-enforced
- ✅ **Automated Testing**: Runs pytest before accepting changes
- ✅ **Human Review Required**: Cannot merge, push, or deploy—only prepare changes for review

## Quick Start

### Using the Orchestrator (Message-Based)

Send a message with the `SELF_UPGRADE` prefix:

```
SELF_UPGRADE: Add debug logging to module X
```

The orchestrator will acknowledge the request and provide guidance on the capability.

### Using the Python API

```python
from self_upgrade.engine import run_self_upgrade

result = run_self_upgrade(
    request="Add debug logging to module X",
    file_edits={
        "module_x.py": "# new file content with logging\n..."
    },
    topic_slug="add-logging-x"
)

print(result.format_summary())
```

## Architecture

### Components

```
self_upgrade/
├── __init__.py          # Public API
├── policy.py            # Policy enforcement (allow/deny lists)
├── runner.py            # Safe command execution
├── git_ops.py           # Git branch operations
└── engine.py            # Orchestration and workflow

milton_orchestrator/
└── self_upgrade_entry.py  # Integration with orchestrator

docs/
└── SELF_UPGRADE_POLICY.md  # Human-readable policy document
```

### Workflow

1. **Request Phase**: Human submits self-upgrade request
2. **Planning Phase**: System analyzes request and creates structured plan
3. **Validation Phase**: Policy enforcement checks files and commands
4. **Execution Phase**:
   - Create branch `self-upgrade/<topic>`
   - Apply file edits
   - Stage and commit changes
   - Run test suite
5. **Evidence Phase**: Generate diff, capture test output, build checklist
6. **Human Review Phase**: Human reviews and decides to merge or abandon

### Integration Point

The orchestrator routing is extended at:
- **File**: `milton_orchestrator/orchestrator.py`
- **Line 746**: Route `SELF_UPGRADE` prefix to handler
- **Line 851-895**: `process_self_upgrade_request()` method
- **Line 1056**: Add `SELF_UPGRADE` to prefix matching list

```python
# In orchestrator.py route_message():
if kind == "SELF_UPGRADE":
    return "SELF_UPGRADE", payload, None
```

## Policy

See [`docs/SELF_UPGRADE_POLICY.md`](../docs/SELF_UPGRADE_POLICY.md) for full policy details.

### Forbidden Operations

- ❌ Direct writes to `main`, `master`, `production`, `deploy` branches
- ❌ `git push`, `git merge`, `git rebase`
- ❌ Edits to secrets: `.env`, `**/secrets/*`, `**/*key*`, `**/*token*`
- ❌ Deployment commands: `systemctl`, `docker-compose up`, service restarts
- ❌ Self-modification without override: `self_upgrade/*`, `docs/SELF_UPGRADE_POLICY.md`

### Allowed Operations

- ✅ Create branch: `git checkout -b self-upgrade/<topic>`
- ✅ Stage/commit: `git add`, `git commit -m`
- ✅ Tests: `pytest -q`
- ✅ Diff generation: `git diff main...HEAD`
- ✅ Edit non-forbidden files

## Examples

### Example 1: Add Logging to a Module

```python
from self_upgrade.engine import run_self_upgrade

result = run_self_upgrade(
    request="Add debug logging to the orchestrator's message handling",
    file_edits={
        "milton_orchestrator/orchestrator.py": """
# ... existing imports ...
import logging

logger = logging.getLogger(__name__)

# ... existing code with added logging ...
logger.debug("Processing message: %s", message_id)
"""
    },
    topic_slug="add-debug-logging"
)

if result.success:
    print(f"✅ Branch: {result.branch_name}")
    print(f"✅ Changed: {len(result.changed_files)} files")
    print(f"✅ Tests: {'PASS' if 'passed' in result.test_output else 'FAIL'}")
    print("\nDiff:")
    print(result.diff_text[:500])
else:
    print(f"❌ {result.status}: {result.error_message}")
```

### Example 2: Check Policy Before Execution

```python
from self_upgrade.policy import validate_files, validate_command

# Check if files are allowed
valid, reason, denied = validate_files([".env", "test.py"])
if not valid:
    print(f"Denied: {reason}")
    # Output: Denied: Denied files: .env

# Check if command is allowed
valid, reason = validate_command("git push origin main")
if not valid:
    print(f"Blocked: {reason}")
    # Output: Blocked: Command matches denied pattern: git\s+push
```

### Example 3: Manual Review Workflow

```bash
# After self-upgrade execution completes:

# 1. Review the diff
git diff main...self-upgrade/add-feature

# 2. Check test results
git log -1 --format="%B"

# 3. Run tests manually (optional)
pytest -q

# 4. If approved, merge
git checkout main
git merge --no-ff self-upgrade/add-feature

# 5. If rejected, delete branch
git branch -D self-upgrade/add-feature
```

## Configuration

Override limits via environment variables:

```bash
# Allow self-upgrade to edit its own files (dangerous!)
export MILTON_SELF_UPGRADE_ALLOW_POLICY_EDITS=1

# Increase file change limit
export MILTON_SELF_UPGRADE_MAX_FILES=20

# Increase LOC change limit
export MILTON_SELF_UPGRADE_MAX_LOC=1000

# Skip tests (dangerous!)
export MILTON_SELF_UPGRADE_SKIP_TESTS=1

# Increase command timeout
export MILTON_SELF_UPGRADE_TIMEOUT=600  # 10 minutes
```

## Testing

Run the self-upgrade test suite:

```bash
pytest tests/test_self_upgrade.py -v
```

Test coverage includes:
- Policy enforcement (protected branches, denied files, denied commands)
- Safe command execution
- Git operations (branch creation, diff generation)
- Engine workflow (happy path and error cases)

## Limitations & Future Work

### Current Limitations

1. **No LLM Integration**: The current implementation provides the workflow infrastructure but does not yet integrate LLM reasoning for:
   - Analyzing self-upgrade requests
   - Scanning the repository to find relevant files
   - Generating appropriate code edits

2. **Manual File Edits**: Users must provide the `file_edits` dictionary manually. Future work should automate this via LLM code generation.

3. **No Multi-Step Plans**: The engine supports a structured `UpgradePlan` but currently executes single-step changes. Complex multi-step refactors are not yet supported.

### Future Enhancements

- [ ] Integrate with LLM for request analysis and code generation
- [ ] Add repository scanning (ripgrep, tree-sitter) for context gathering
- [ ] Support multi-step upgrade plans with rollback
- [ ] Add diff preview before execution
- [ ] Implement approval queue for asynchronous human review
- [ ] Add telemetry and audit logs for security monitoring

## Safety & Security

### Design Principles

1. **Defense in Depth**: Multiple layers of policy enforcement (file patterns, commands, branches)
2. **Fail-Safe Defaults**: All operations denied by default; must be explicitly allowed
3. **Audit Trail**: All commands and changes are logged
4. **Human-in-the-Loop**: No autonomous merge/deploy; human review required
5. **Minimal Trust**: Self-upgrade cannot modify its own policy without override

### Incident Response

If a self-upgrade goes wrong:

1. **Stop execution**: Ctrl+C or kill the process
2. **Inspect branch**: `git diff main...self-upgrade/<topic>`
3. **Delete branch**: `git branch -D self-upgrade/<topic>`
4. **Review logs**: Check `agent_logging/` for command audit trail
5. **Report issue**: File bug with reproduction steps

## References

- Policy document: [`docs/SELF_UPGRADE_POLICY.md`](../docs/SELF_UPGRADE_POLICY.md)
- Test suite: [`tests/test_self_upgrade.py`](../tests/test_self_upgrade.py)
- Integration point: [`milton_orchestrator/orchestrator.py`](../milton_orchestrator/orchestrator.py) (lines 746, 851-895, 1056)
