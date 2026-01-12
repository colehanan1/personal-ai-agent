"""
Self-upgrade engine: planning and execution.

Orchestrates the supervised self-upgrade workflow.
"""
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .git_ops import GitOperations
from .policy import (
    validate_files,
    get_max_files_changed,
    get_max_loc_changed,
    skip_tests,
)
from .runner import SafeCommandRunner

logger = logging.getLogger(__name__)


@dataclass
class UpgradePlan:
    """Structured plan for self-upgrade."""
    goal: str
    files_to_touch: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    verification_commands: List[str] = field(default_factory=lambda: ["pytest -q"])
    risk_notes: str = ""
    max_files: int = 10
    max_loc: int = 400


@dataclass
class SelfUpgradeResult:
    """Result of self-upgrade execution."""
    success: bool
    status: str  # "SUCCESS", "BLOCKED_BY_POLICY", "GIT_ERROR", "TEST_FAILURE", etc.
    branch_name: Optional[str] = None
    changed_files: List[str] = field(default_factory=list)
    diff_text: str = ""
    test_output: str = ""
    verification_checklist: List[str] = field(default_factory=list)
    error_message: str = ""
    
    def format_summary(self) -> str:
        """Format result as human-readable summary."""
        lines = [
            f"## Self-Upgrade Result: {self.status}",
            "",
        ]
        
        if self.success:
            lines.extend([
                f"✅ Branch: {self.branch_name}",
                f"✅ Files changed: {len(self.changed_files)}",
                "",
                "### Changed Files:",
            ])
            for f in self.changed_files:
                lines.append(f"  - {f}")
            
            lines.extend([
                "",
                "### Test Output:",
                self.test_output[:500] + ("..." if len(self.test_output) > 500 else ""),
                "",
                "### Verification Checklist:",
            ])
            for item in self.verification_checklist:
                lines.append(f"  {item}")
            
            lines.extend([
                "",
                "### Next Steps:",
                f"  1. Review diff: `git diff main...{self.branch_name}`",
                "  2. Review changes carefully",
                "  3. If approved: `git checkout main && git merge --no-ff " + self.branch_name + "`",
                f"  4. If rejected: `git branch -D {self.branch_name}`",
            ])
        else:
            lines.extend([
                f"❌ Error: {self.error_message}",
                "",
                f"Status: {self.status}",
            ])
        
        return "\n".join(lines)


class SelfUpgradeEngine:
    """Engine for supervised self-upgrade execution."""
    
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.runner = SafeCommandRunner(repo_root, log_prefix="SELF_UPGRADE")
        self.git_ops = GitOperations(repo_root, self.runner)
    
    def plan_upgrade(self, request: str) -> UpgradePlan:
        """
        Create an upgrade plan from free-form request.
        
        This is a simplified implementation. In production, this would
        use LLM reasoning to generate a detailed plan.
        
        Args:
            request: Free-form upgrade request
        
        Returns:
            Structured UpgradePlan
        """
        # Extract goal (first sentence or first 100 chars)
        goal = request.split(".")[0][:100]
        
        # Set limits from policy
        max_files = get_max_files_changed()
        max_loc = get_max_loc_changed()
        
        plan = UpgradePlan(
            goal=goal,
            max_files=max_files,
            max_loc=max_loc,
            risk_notes="Automated self-upgrade - requires human review",
        )
        
        logger.info(f"[PLAN] Created upgrade plan: {goal}")
        return plan
    
    def execute_upgrade(
        self,
        plan: UpgradePlan,
        file_edits: dict[str, str],
        topic_slug: str,
    ) -> SelfUpgradeResult:
        """
        Execute self-upgrade with given plan and file edits.
        
        Args:
            plan: Structured upgrade plan
            file_edits: Dict mapping file paths to new content
            topic_slug: Short slug for branch name
        
        Returns:
            SelfUpgradeResult with execution details
        """
        logger.info(f"[EXECUTE] Starting self-upgrade: {plan.goal}")
        
        try:
            # 1. Check we're not on main
            self.git_ops.ensure_not_on_main()
            
            # 2. Validate files
            file_paths = list(file_edits.keys())
            files_valid, reason, denied = validate_files(file_paths)
            if not files_valid:
                return SelfUpgradeResult(
                    success=False,
                    status="BLOCKED_BY_POLICY",
                    error_message=f"File validation failed: {reason}",
                )
            
            # 3. Check file count limit
            if len(file_paths) > plan.max_files:
                return SelfUpgradeResult(
                    success=False,
                    status="BLOCKED_BY_POLICY",
                    error_message=f"Too many files ({len(file_paths)} > {plan.max_files})",
                )
            
            # 4. Create branch
            try:
                branch_name = self.git_ops.create_branch(topic_slug)
            except Exception as e:
                return SelfUpgradeResult(
                    success=False,
                    status="GIT_ERROR",
                    error_message=f"Failed to create branch: {e}",
                )
            
            # 5. Apply file edits
            try:
                for file_path, content in file_edits.items():
                    full_path = self.repo_root / file_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding="utf-8")
                    logger.info(f"[EDIT] Wrote {len(content)} bytes to {file_path}")
            except Exception as e:
                return SelfUpgradeResult(
                    success=False,
                    status="FILE_WRITE_ERROR",
                    branch_name=branch_name,
                    error_message=f"Failed to write files: {e}",
                )
            
            # 6. Stage and commit
            try:
                self.git_ops.stage_files(file_paths)
                self.git_ops.commit_changes(f"Self-upgrade: {plan.goal}")
            except Exception as e:
                return SelfUpgradeResult(
                    success=False,
                    status="GIT_ERROR",
                    branch_name=branch_name,
                    error_message=f"Failed to commit: {e}",
                )
            
            # 7. Run tests (unless skipped)
            test_output = ""
            if not skip_tests():
                try:
                    for cmd in plan.verification_commands:
                        result = self.runner.run(cmd, timeout=300)
                        test_output += f"$ {cmd}\n{result.stdout}\n{result.stderr}\n"
                        if not result.success:
                            return SelfUpgradeResult(
                                success=False,
                                status="TEST_FAILURE",
                                branch_name=branch_name,
                                changed_files=file_paths,
                                test_output=test_output,
                                error_message="Tests failed",
                            )
                except Exception as e:
                    return SelfUpgradeResult(
                        success=False,
                        status="TEST_ERROR",
                        branch_name=branch_name,
                        changed_files=file_paths,
                        error_message=f"Test execution failed: {e}",
                    )
            else:
                test_output = "(Tests skipped via MILTON_SELF_UPGRADE_SKIP_TESTS=1)"
            
            # 8. Generate diff
            try:
                diff_text = self.git_ops.generate_diff()
            except Exception as e:
                logger.warning(f"Failed to generate diff: {e}")
                diff_text = "(Diff generation failed)"
            
            # 9. Build verification checklist
            checklist = [
                f"[{'x' if branch_name else ' '}] Branch created (not on main/master)",
                f"[{'x' if not skip_tests() else ' '}] Tests pass",
                f"[{'x' if files_valid else ' '}] No forbidden files modified",
                "[ ] No secrets exposed (human review required)",
                "[ ] Changes are minimal and surgical (human review required)",
                "[ ] Documentation updated if applicable (human review required)",
            ]
            
            # 10. Success
            return SelfUpgradeResult(
                success=True,
                status="SUCCESS",
                branch_name=branch_name,
                changed_files=file_paths,
                diff_text=diff_text,
                test_output=test_output,
                verification_checklist=checklist,
            )
        
        except Exception as e:
            logger.error(f"[EXECUTE] Unexpected error: {e}", exc_info=True)
            # Determine error type based on context
            if "protected branch" in str(e).lower() or "git" in str(e).lower():
                status = "GIT_ERROR"
            else:
                status = "UNEXPECTED_ERROR"
            return SelfUpgradeResult(
                success=False,
                status=status,
                error_message=str(e),
            )


def run_self_upgrade(
    request: str,
    file_edits: dict[str, str],
    topic_slug: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> SelfUpgradeResult:
    """
    Main entry point for self-upgrade execution.
    
    Args:
        request: Free-form upgrade request
        file_edits: Dict mapping file paths to new content
        topic_slug: Short slug for branch name (auto-generated if None)
        repo_root: Repository root (uses cwd if None)
    
    Returns:
        SelfUpgradeResult with execution details
    """
    if repo_root is None:
        repo_root = Path.cwd()
    
    if topic_slug is None:
        # Generate from request
        topic_slug = re.sub(r"[^a-z0-9-]", "-", request[:50].lower()).strip("-")
    
    engine = SelfUpgradeEngine(repo_root)
    plan = engine.plan_upgrade(request)
    result = engine.execute_upgrade(plan, file_edits, topic_slug)
    
    return result
