# Milton Self-Upgrade Policy

## Purpose
This policy governs Milton's supervised self-upgrade capability, enabling the agent to propose, implement, and test code changes in a controlled, branch-based workflow while maintaining strict security and operational boundaries.

## Core Principles

### 1. Supervised Maintainer Model
- Milton can propose and implement code changes
- All changes occur in isolated git branches
- Human review and approval is **required** before merge
- Milton **cannot** merge, push, or deploy changes

### 2. Branch-Only Operations
- Changes must occur on a new branch: `self-upgrade/<topic>`
- Milton **must not** operate on protected branches: `main`, `master`, `production`, `deploy`
- Branch creation and commits are allowed; push/merge are forbidden

### 3. Evidence Requirements
Every self-upgrade execution must produce:
- Clear goal statement (one sentence)
- List of files modified
- Full diff against base branch
- Test execution output (pytest)
- Risk assessment notes
- Pre-filled verification checklist

## Forbidden Operations

### Security-Sensitive Areas (Never Editable)
- **Credentials & Secrets**: `**/.env`, `**/secrets/*`, `**/*key*`, `**/*token*`, `**/id_rsa*`, `**/credentials/*`
- **Production Configs**: `**/config/prod*`, `**/production/*`
- **Network Exposure**: `docker-compose*.yml` (if modifying port mappings)
- **System Configs**: `systemd/*`, `deployment/*` (deployment automation)

### Forbidden Directories (No Editing)
- `.git/` (git internals)
- `logs/` (runtime logs)
- `outputs/` (generated outputs)
- `cache/` (cached data)
- `__pycache__/` (Python cache)

### Forbidden Commands
- **Git Operations**: `git push`, `git merge`, `git rebase`, `git commit --amend`, `git checkout main`, `git checkout master`
- **Deployment**: `systemctl`, `docker-compose up`, `docker-compose restart`, service restarts
- **Network Changes**: `ufw`, `iptables`, firewall modifications
- **System Modifications**: package installs without explicit approval

### Self-Modification Restrictions
- Editing files within `self_upgrade/` requires explicit human override
- Editing `docs/SELF_UPGRADE_POLICY.md` requires explicit human override
- Override flag: `MILTON_SELF_UPGRADE_ALLOW_POLICY_EDITS=1` (default: OFF)

## Allowed Operations

### Git Operations (Branch Context Only)
- `git status` - check repository state
- `git checkout -b self-upgrade/<topic>` - create new branch
- `git add <allowed-files>` - stage non-forbidden files
- `git commit -m "<message>"` - commit changes (new commits only)
- `git diff main...HEAD` - generate diff against base

### Testing & Verification
- `pytest -q` - run test suite
- `pytest -q <specific-test>` - run targeted tests
- Static analysis tools (if present)

### File Operations
- Read any file (for analysis)
- Edit non-forbidden files (with policy checks)
- Create new files (with policy checks)

## Operational Limits

### Change Boundaries
- **MAX_FILES_CHANGED**: 10 files per self-upgrade (unless explicitly overridden)
- **MAX_LOC_CHANGED**: 400 lines of code per self-upgrade (unless explicitly overridden)
- **Command Timeout**: 300 seconds (5 minutes) per command

### Execution Constraints
- All commands run with explicit timeouts
- All commands are logged (command, cwd, exit code, duration)
- Failed commands abort the self-upgrade workflow
- Test failures abort the self-upgrade workflow (unless overridden)

## Workflow

### 1. Request Phase
- Human submits self-upgrade request (free-form text)
- Milton validates request against policy

### 2. Planning Phase
- Milton scans repository to identify relevant files
- Generates structured plan:
  - Goal statement
  - Files to modify
  - Proposed changes (patch-level detail)
  - Verification commands
  - Risk notes

### 3. Execution Phase
- Create branch: `self-upgrade/<slug>`
- Verify not on protected branch (hard fail if violated)
- Apply file edits (direct Python file operations)
- Stage and commit changes
- Run test suite (`pytest -q`)

### 4. Evidence Phase
- Generate diff: `git diff main...HEAD`
- Capture test output
- Compile verification checklist:
  - [ ] Branch created (not on main/master)
  - [ ] Tests pass
  - [ ] No forbidden files modified
  - [ ] No secrets exposed
  - [ ] Changes are minimal and surgical
  - [ ] Documentation updated (if applicable)

### 5. Human Review Phase
- Milton presents evidence to human
- Human reviews diff, tests, and checklist
- Human decides: approve (merge) or reject (abandon branch)

## Failure Modes

### Policy Violation
- Immediate abort with clear error message
- No changes committed
- Return `BLOCKED_BY_POLICY` status with explanation

### Test Failure
- Abort unless explicit override provided
- Present test output for human review
- Option to proceed with human acknowledgment

### Git Operation Failure
- Abort with git error details
- Do not attempt workarounds
- Return `GIT_ERROR` status

## Logging & Audit Trail

### Command Logging
Every command execution is logged:
```
[timestamp] COMMAND: <command>
[timestamp] CWD: <working-directory>
[timestamp] EXIT_CODE: <code>
[timestamp] DURATION: <seconds>
[timestamp] STDOUT: <captured-output>
[timestamp] STDERR: <captured-errors>
```

### Self-Upgrade Logging
Each self-upgrade attempt is logged:
```
[timestamp] SELF_UPGRADE_START: request_id=<id> goal=<goal>
[timestamp] BRANCH_CREATED: <branch-name>
[timestamp] FILES_MODIFIED: <count> files
[timestamp] TESTS_RUN: result=<pass/fail>
[timestamp] SELF_UPGRADE_COMPLETE: status=<status>
```

## Human Override Mechanisms

### Explicit Overrides (Environment Variables)
- `MILTON_SELF_UPGRADE_ALLOW_POLICY_EDITS=1` - allow self_upgrade/ modifications
- `MILTON_SELF_UPGRADE_MAX_FILES=<N>` - override file count limit
- `MILTON_SELF_UPGRADE_MAX_LOC=<N>` - override LOC limit
- `MILTON_SELF_UPGRADE_SKIP_TESTS=1` - skip test execution (dangerous)

### Emergency Stop
- Ctrl+C or process termination stops self-upgrade immediately
- Partial commits may exist on branch (can be reset)

## Compliance

### Security Audit
- This policy itself is version-controlled
- Changes to this policy require human review
- Self-upgrade cannot weaken this policy

### Testing Requirements
- All self-upgrade code paths must have unit tests
- Mock external dependencies (git, pytest)
- Test both happy paths and policy violations

## Version
- Version: 1.0
- Last Updated: 2026-01-12
- Next Review: When self-upgrade capabilities expand
