"""
Tests for self-upgrade capability.

Validates policy enforcement, git operations, and workflow.
"""
import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from self_upgrade.policy import (
    is_protected_branch,
    is_denied_file,
    is_denied_command,
    is_allowed_command,
    validate_command,
    validate_files,
    is_self_upgrade_protected,
    allow_self_upgrade_edits,
)
from self_upgrade.runner import SafeCommandRunner, CommandResult
from self_upgrade.git_ops import GitOperations, GitStatus
from self_upgrade.engine import SelfUpgradeEngine, run_self_upgrade


class TestPolicy:
    """Test policy enforcement rules."""
    
    def test_protected_branches(self):
        """Test protected branch detection."""
        assert is_protected_branch("main")
        assert is_protected_branch("master")
        assert is_protected_branch("production")
        assert not is_protected_branch("self-upgrade/test")
        assert not is_protected_branch("feature/test")
    
    def test_denied_files(self):
        """Test denied file pattern matching."""
        assert is_denied_file(".env")
        assert is_denied_file("secrets/api_key.txt")
        assert is_denied_file("config/prod_settings.py")
        assert is_denied_file(".git/config")
        assert is_denied_file("logs/output.log")
        assert not is_denied_file("milton_orchestrator/config.py")
        assert not is_denied_file("tests/test_example.py")
    
    def test_self_upgrade_protected_files(self):
        """Test self-upgrade protected file detection."""
        assert is_self_upgrade_protected("self_upgrade/policy.py")
        assert is_self_upgrade_protected("docs/SELF_UPGRADE_POLICY.md")
        assert not is_self_upgrade_protected("milton_orchestrator/orchestrator.py")
    
    def test_denied_commands(self):
        """Test denied command patterns."""
        denied, _ = is_denied_command("git push origin main")
        assert denied
        
        denied, _ = is_denied_command("git merge feature/test")
        assert denied
        
        denied, _ = is_denied_command("systemctl restart milton")
        assert denied
        
        denied, _ = is_denied_command("git checkout main")
        assert denied
        
        denied, _ = is_denied_command("rm -rf /")
        assert denied
    
    def test_allowed_commands(self):
        """Test allowed command patterns."""
        allowed, _ = is_allowed_command("git status")
        assert allowed
        
        allowed, _ = is_allowed_command("git checkout -b self-upgrade/test")
        assert allowed
        
        allowed, _ = is_allowed_command("pytest -q")
        assert allowed
        
        allowed, _ = is_allowed_command("git diff main...HEAD")
        assert allowed
    
    def test_validate_command_denied(self):
        """Test command validation rejects denied commands."""
        valid, reason = validate_command("git push origin main")
        assert not valid
        assert "denied" in reason.lower()
    
    def test_validate_command_not_allowed(self):
        """Test command validation rejects non-allowed commands."""
        valid, reason = validate_command("curl http://example.com")
        assert not valid
        assert "allowed" in reason.lower()
    
    def test_validate_command_allowed(self):
        """Test command validation accepts allowed commands."""
        valid, reason = validate_command("git status")
        assert valid
        
        valid, reason = validate_command("pytest -q tests/")
        assert valid
    
    def test_validate_files_denied(self):
        """Test file validation rejects denied files."""
        valid, reason, denied = validate_files([".env", "test.py"])
        assert not valid
        assert ".env" in denied
    
    def test_validate_files_protected_without_override(self):
        """Test file validation rejects self-upgrade files without override."""
        os.environ.pop("MILTON_SELF_UPGRADE_ALLOW_POLICY_EDITS", None)
        valid, reason, protected = validate_files(["self_upgrade/policy.py"])
        assert not valid
        assert "self_upgrade/policy.py" in reason
    
    def test_validate_files_protected_with_override(self):
        """Test file validation accepts self-upgrade files with override."""
        os.environ["MILTON_SELF_UPGRADE_ALLOW_POLICY_EDITS"] = "1"
        try:
            valid, reason, _ = validate_files(["self_upgrade/policy.py"])
            assert valid
        finally:
            os.environ.pop("MILTON_SELF_UPGRADE_ALLOW_POLICY_EDITS", None)
    
    def test_validate_files_allowed(self):
        """Test file validation accepts allowed files."""
        valid, reason, _ = validate_files(["test.py", "src/module.py"])
        assert valid


class TestRunner:
    """Test safe command runner."""
    
    def test_runner_denies_forbidden_command(self, tmp_path):
        """Test runner refuses to execute denied commands."""
        runner = SafeCommandRunner(tmp_path)
        
        with pytest.raises(ValueError, match="denied by policy"):
            runner.run("git push origin main")
    
    def test_runner_executes_allowed_command(self, tmp_path):
        """Test runner executes allowed commands."""
        runner = SafeCommandRunner(tmp_path)
        
        result = runner.run("echo 'test'")
        assert result.success
        assert result.exit_code == 0
        assert "test" in result.stdout
    
    def test_runner_captures_failure(self, tmp_path):
        """Test runner captures command failures."""
        runner = SafeCommandRunner(tmp_path)
        
        result = runner.run("ls /nonexistent/path/that/does/not/exist")
        assert not result.success
        assert result.exit_code != 0
        assert result.stderr
    
    def test_runner_checked_raises_on_failure(self, tmp_path):
        """Test runner_checked raises on command failure."""
        runner = SafeCommandRunner(tmp_path)
        
        with pytest.raises(RuntimeError, match="Command failed"):
            runner.run_checked("ls /nonexistent/path")


class TestGitOperations:
    """Test git operations."""
    
    @patch("self_upgrade.git_ops.SafeCommandRunner")
    def test_get_current_branch(self, mock_runner_class):
        """Test getting current branch."""
        mock_runner = Mock()
        mock_runner_class.return_value = mock_runner
        mock_runner.run.return_value = CommandResult(
            command="git branch --show-current",
            cwd=".",
            exit_code=0,
            stdout="feature/test\n",
            stderr="",
            duration=0.1,
            success=True,
        )
        
        git_ops = GitOperations(Path("."), mock_runner)
        branch = git_ops.get_current_branch()
        
        assert branch == "feature/test"
    
    @patch("self_upgrade.git_ops.SafeCommandRunner")
    def test_ensure_not_on_main_raises_if_on_main(self, mock_runner_class):
        """Test ensure_not_on_main raises when on protected branch."""
        mock_runner = Mock()
        mock_runner_class.return_value = mock_runner
        mock_runner.run.side_effect = [
            # get_current_branch
            CommandResult(
                command="git branch --show-current",
                cwd=".",
                exit_code=0,
                stdout="main\n",
                stderr="",
                duration=0.1,
                success=True,
            ),
            # get_status porcelain
            CommandResult(
                command="git status --porcelain",
                cwd=".",
                exit_code=0,
                stdout="",
                stderr="",
                duration=0.1,
                success=True,
            ),
        ]
        
        git_ops = GitOperations(Path("."), mock_runner)
        
        with pytest.raises(RuntimeError, match="protected branch"):
            git_ops.ensure_not_on_main()
    
    @patch("self_upgrade.git_ops.SafeCommandRunner")
    def test_ensure_not_on_main_passes_on_feature_branch(self, mock_runner_class):
        """Test ensure_not_on_main passes when on feature branch."""
        mock_runner = Mock()
        mock_runner_class.return_value = mock_runner
        mock_runner.run.side_effect = [
            # get_current_branch
            CommandResult(
                command="git branch --show-current",
                cwd=".",
                exit_code=0,
                stdout="feature/test\n",
                stderr="",
                duration=0.1,
                success=True,
            ),
            # get_status porcelain
            CommandResult(
                command="git status --porcelain",
                cwd=".",
                exit_code=0,
                stdout="",
                stderr="",
                duration=0.1,
                success=True,
            ),
        ]
        
        git_ops = GitOperations(Path("."), mock_runner)
        git_ops.ensure_not_on_main()  # Should not raise
    
    @patch("self_upgrade.git_ops.SafeCommandRunner")
    def test_create_branch(self, mock_runner_class):
        """Test creating self-upgrade branch."""
        mock_runner = Mock()
        mock_runner_class.return_value = mock_runner
        mock_runner.run_checked.return_value = CommandResult(
            command="git checkout -b self-upgrade/test-feature",
            cwd=".",
            exit_code=0,
            stdout="",
            stderr="",
            duration=0.1,
            success=True,
        )
        
        git_ops = GitOperations(Path("."), mock_runner)
        branch = git_ops.create_branch("Test Feature")
        
        assert branch == "self-upgrade/test-feature"
        mock_runner.run_checked.assert_called_once()


class TestEngine:
    """Test self-upgrade engine."""
    
    @patch("self_upgrade.engine.SafeCommandRunner")
    @patch("self_upgrade.engine.GitOperations")
    def test_execute_upgrade_blocks_on_main_branch(self, mock_git_class, mock_runner_class, tmp_path):
        """Test execution blocks when on main branch."""
        mock_git = Mock()
        mock_git_class.return_value = mock_git
        mock_git.ensure_not_on_main.side_effect = RuntimeError("protected branch")
        
        engine = SelfUpgradeEngine(tmp_path)
        
        from self_upgrade.engine import UpgradePlan
        plan = UpgradePlan(goal="Test upgrade")
        
        result = engine.execute_upgrade(plan, {"test.py": "content"}, "test")
        
        assert not result.success
        assert result.status == "GIT_ERROR"
        assert "protected branch" in result.error_message.lower()
    
    @patch("self_upgrade.engine.SafeCommandRunner")
    @patch("self_upgrade.engine.GitOperations")
    def test_execute_upgrade_blocks_denied_files(self, mock_git_class, mock_runner_class, tmp_path):
        """Test execution blocks when editing denied files."""
        mock_git = Mock()
        mock_git_class.return_value = mock_git
        mock_git.ensure_not_on_main.return_value = None
        
        engine = SelfUpgradeEngine(tmp_path)
        
        from self_upgrade.engine import UpgradePlan
        plan = UpgradePlan(goal="Test upgrade")
        
        result = engine.execute_upgrade(plan, {".env": "SECRET=value"}, "test")
        
        assert not result.success
        assert result.status == "BLOCKED_BY_POLICY"
        assert "denied" in result.error_message.lower() or "file" in result.error_message.lower()
    
    @patch("self_upgrade.engine.SafeCommandRunner")
    @patch("self_upgrade.engine.GitOperations")
    def test_execute_upgrade_happy_path(self, mock_git_class, mock_runner_class, tmp_path):
        """Test successful upgrade execution."""
        # Mock git operations
        mock_git = Mock()
        mock_git_class.return_value = mock_git
        mock_git.ensure_not_on_main.return_value = None
        mock_git.create_branch.return_value = "self-upgrade/test"
        mock_git.stage_files.return_value = None
        mock_git.commit_changes.return_value = None
        mock_git.generate_diff.return_value = "diff --git a/test.py b/test.py\n+test content"
        
        # Mock test runner
        mock_runner = Mock()
        mock_runner_class.return_value = mock_runner
        mock_runner.run.return_value = CommandResult(
            command="pytest -q",
            cwd=str(tmp_path),
            exit_code=0,
            stdout="5 passed in 0.5s",
            stderr="",
            duration=0.5,
            success=True,
        )
        
        engine = SelfUpgradeEngine(tmp_path)
        
        from self_upgrade.engine import UpgradePlan
        plan = UpgradePlan(goal="Add test file")
        
        result = engine.execute_upgrade(plan, {"test.py": "# test content"}, "test")
        
        assert result.success
        assert result.status == "SUCCESS"
        assert result.branch_name == "self-upgrade/test"
        assert "test.py" in result.changed_files
        assert result.test_output
        assert result.diff_text
        assert len(result.verification_checklist) > 0


class TestIntegration:
    """Integration tests for self-upgrade workflow."""
    
    def test_run_self_upgrade_interface(self, tmp_path):
        """Test run_self_upgrade provides correct interface."""
        # This tests the public API shape
        with patch("self_upgrade.engine.SelfUpgradeEngine") as mock_engine_class:
            mock_engine = Mock()
            mock_engine_class.return_value = mock_engine
            mock_engine.plan_upgrade.return_value = Mock(goal="test", max_files=10, max_loc=400)
            mock_engine.execute_upgrade.return_value = Mock(
                success=True,
                status="SUCCESS",
                branch_name="self-upgrade/test",
                format_summary=Mock(return_value="summary"),
            )
            
            result = run_self_upgrade(
                request="Add logging",
                file_edits={"test.py": "content"},
                topic_slug="add-logging",
                repo_root=tmp_path,
            )
            
            assert hasattr(result, "success")
            assert hasattr(result, "status")
            assert hasattr(result, "format_summary")
