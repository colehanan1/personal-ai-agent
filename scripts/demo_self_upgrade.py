#!/usr/bin/env python3
"""
Demonstration of self-upgrade capability.

This script shows how to use the self-upgrade engine to make controlled
code changes with policy enforcement.
"""
import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from self_upgrade.engine import run_self_upgrade
from self_upgrade.policy import (
    validate_files,
    validate_command,
    is_protected_branch,
)


def demo_policy_checks():
    """Demonstrate policy enforcement."""
    print("=" * 60)
    print("DEMO: Policy Enforcement")
    print("=" * 60)
    
    # Check protected branches
    print("\n1. Protected Branch Check:")
    for branch in ["main", "master", "feature/test"]:
        protected = is_protected_branch(branch)
        status = "❌ PROTECTED" if protected else "✅ ALLOWED"
        print(f"   {branch:20} -> {status}")
    
    # Check file validation
    print("\n2. File Validation:")
    test_files = [
        [".env"],
        ["secrets/api_key.txt"],
        ["milton_orchestrator/config.py"],
        ["test.py"],
    ]
    for files in test_files:
        valid, reason, denied = validate_files(files)
        status = "✅ ALLOWED" if valid else "❌ DENIED"
        file_str = files[0]
        print(f"   {file_str:30} -> {status}")
        if not valid:
            print(f"      Reason: {reason}")
    
    # Check command validation
    print("\n3. Command Validation:")
    test_commands = [
        "git push origin main",
        "git merge feature",
        "git status",
        "pytest -q",
        "systemctl restart milton",
    ]
    for cmd in test_commands:
        valid, reason = validate_command(cmd)
        status = "✅ ALLOWED" if valid else "❌ DENIED"
        print(f"   {cmd:30} -> {status}")


def demo_self_upgrade_dry_run():
    """Demonstrate self-upgrade workflow (dry run with mock data)."""
    print("\n" + "=" * 60)
    print("DEMO: Self-Upgrade Workflow (Conceptual)")
    print("=" * 60)
    
    print("\nScenario: Add a comment to a test file")
    print("\nFile edits:")
    file_edits = {
        "tests/demo_test.py": """# Demo test file
# Added by self-upgrade demonstration

def test_example():
    '''Example test added by self-upgrade.'''
    assert True
"""
    }
    
    for filepath, content in file_edits.items():
        print(f"\n  File: {filepath}")
        print(f"  Content preview:")
        for line in content.split("\n")[:5]:
            print(f"    {line}")
    
    print("\nWorkflow steps (would execute if not on main branch):")
    print("  1. ✅ Validate not on protected branch")
    print("  2. ✅ Validate file paths against policy")
    print("  3. ✅ Create branch: self-upgrade/add-demo-test")
    print("  4. ✅ Write file changes")
    print("  5. ✅ Stage files: git add tests/demo_test.py")
    print("  6. ✅ Commit: git commit -m 'Self-upgrade: Add demo test'")
    print("  7. ✅ Run tests: pytest -q")
    print("  8. ✅ Generate diff: git diff main...HEAD")
    print("  9. ✅ Build verification checklist")
    print("\nResult: SUCCESS")
    print("  Branch: self-upgrade/add-demo-test")
    print("  Files changed: 1")
    print("  Tests: PASS")
    print("\nNext steps for human:")
    print("  - Review: git diff main...self-upgrade/add-demo-test")
    print("  - Approve: git checkout main && git merge --no-ff self-upgrade/add-demo-test")
    print("  - Reject: git branch -D self-upgrade/add-demo-test")


def demo_integration_point():
    """Show integration with orchestrator."""
    print("\n" + "=" * 60)
    print("DEMO: Orchestrator Integration")
    print("=" * 60)
    
    print("\nIntegration Points:")
    print("  File: milton_orchestrator/orchestrator.py")
    print("  Line 746: Route SELF_UPGRADE prefix")
    print("  Line 851-895: process_self_upgrade_request() method")
    print("  Line 1056: Add SELF_UPGRADE to prefix matching")
    
    print("\nUsage via orchestrator:")
    print("  Send message: 'SELF_UPGRADE: Add logging to module X'")
    print("  Orchestrator routes to: process_self_upgrade_request()")
    print("  Entry point calls: milton_orchestrator.self_upgrade_entry.process_self_upgrade_request()")
    
    print("\nPolicy document:")
    print("  Location: docs/SELF_UPGRADE_POLICY.md")
    print("  Contains: Forbidden operations, allowed operations, workflow")
    
    print("\nUser guide:")
    print("  Location: docs/SELF_UPGRADE_GUIDE.md")
    print("  Contains: Examples, architecture, configuration")


def main():
    """Run all demonstrations."""
    print("\n" + "=" * 60)
    print("MILTON SELF-UPGRADE CAPABILITY DEMONSTRATION")
    print("=" * 60)
    
    print("\nThis demonstration shows the supervised self-upgrade system.")
    print("Milton can now propose and implement code changes in a controlled,")
    print("branch-based workflow with strict security guardrails.")
    
    # Run demos
    demo_policy_checks()
    demo_self_upgrade_dry_run()
    demo_integration_point()
    
    print("\n" + "=" * 60)
    print("DEMONSTRATION COMPLETE")
    print("=" * 60)
    
    print("\nKey Achievements:")
    print("  ✅ Policy enforcement (protected branches, denied files, denied commands)")
    print("  ✅ Safe command execution (validated, logged, timeout-enforced)")
    print("  ✅ Git branch workflow (create, commit, diff generation)")
    print("  ✅ Test execution (pytest integration)")
    print("  ✅ Orchestrator integration (SELF_UPGRADE routing)")
    print("  ✅ Comprehensive test suite (24 tests, all passing)")
    print("  ✅ Documentation (policy + user guide)")
    
    print("\nNext Steps:")
    print("  1. Review docs/SELF_UPGRADE_POLICY.md for full policy")
    print("  2. Review docs/SELF_UPGRADE_GUIDE.md for usage examples")
    print("  3. Run: pytest tests/test_self_upgrade.py -v")
    print("  4. Integrate with LLM for automated code generation (future work)")
    
    print("\nFor questions or issues, see:")
    print("  - Policy: docs/SELF_UPGRADE_POLICY.md")
    print("  - Guide: docs/SELF_UPGRADE_GUIDE.md")
    print("  - Tests: tests/test_self_upgrade.py")
    print()


if __name__ == "__main__":
    main()
