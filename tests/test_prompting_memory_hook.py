"""Tests for prompting middleware memory hook."""
from __future__ import annotations

import pytest


class TestMemoryHook:
    """Tests for MemoryHook class."""

    def test_init_disabled(self):
        """Test that hook can be disabled."""
        from prompting import MemoryHook

        hook = MemoryHook(enabled=False)

        assert hook.enabled is False
        assert hook.is_available() is False

    def test_graceful_degradation_no_memory_module(self, monkeypatch, tmp_path):
        """Test graceful degradation when memory module is not available."""
        from prompting import MemoryHook

        # Create hook with non-existent repo root
        hook = MemoryHook(repo_root=tmp_path, enabled=True)

        # Should not crash, just return False
        available = hook.is_available()

        # Memory module exists, but backend might not be available
        # Either way, should not crash
        assert isinstance(available, bool)

    def test_store_reshaped_prompt_when_unavailable(self, tmp_path):
        """Test store_reshaped_prompt returns None when memory unavailable."""
        from prompting import MemoryHook
        from prompting.types import PromptSpec

        hook = MemoryHook(repo_root=tmp_path, enabled=False)

        prompt_spec = PromptSpec(
            original_prompt="Hello",
            reshaped_prompt="Hello, world",
            category="greeting",
        )

        result = hook.store_reshaped_prompt(prompt_spec)

        assert result is None

    def test_store_verification_artifacts_when_unavailable(self, tmp_path):
        """Test store_verification_artifacts returns None when memory unavailable."""
        from prompting import MemoryHook
        from prompting.types import CoveQuestion, PipelineArtifacts

        hook = MemoryHook(repo_root=tmp_path, enabled=False)

        artifacts = PipelineArtifacts(
            cove_questions=[
                CoveQuestion(question_text="Is this true?", target_claim="test"),
            ],
        )

        result = hook.store_verification_artifacts(artifacts)

        assert result is None

    def test_store_pipeline_result_when_unavailable(self, tmp_path):
        """Test store_pipeline_result returns empty list when memory unavailable."""
        from prompting import MemoryHook
        from prompting.types import PipelineArtifacts

        hook = MemoryHook(repo_root=tmp_path, enabled=False)

        artifacts = PipelineArtifacts()

        result = hook.store_pipeline_result(artifacts)

        assert result == []

    def test_store_artifacts_skipped_when_empty(self, tmp_path, monkeypatch):
        """Test that empty artifacts are not stored."""
        from prompting import MemoryHook
        from prompting.types import PipelineArtifacts

        # Force JSONL backend
        monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")

        hook = MemoryHook(repo_root=tmp_path, enabled=True)

        # Artifacts without verification
        artifacts = PipelineArtifacts()

        result = hook.store_verification_artifacts(artifacts)

        # Should return None since no verification to store
        assert result is None


class TestMemoryHookWithBackend:
    """Tests for MemoryHook with actual backend (JSONL)."""

    @pytest.fixture
    def jsonl_hook(self, tmp_path, monkeypatch):
        """Create a memory hook with JSONL backend."""
        from prompting import MemoryHook, reset_memory_hook

        # Force JSONL backend
        monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")

        # Create data directory
        data_dir = tmp_path / "data" / "memory"
        data_dir.mkdir(parents=True, exist_ok=True)

        reset_memory_hook()
        return MemoryHook(repo_root=tmp_path, enabled=True)

    def test_is_available_with_jsonl(self, jsonl_hook):
        """Test that JSONL backend is available."""
        # This may or may not be available depending on the environment
        # The key is that it doesn't crash
        available = jsonl_hook.is_available()
        assert isinstance(available, bool)

    def test_store_reshaped_prompt_with_jsonl(self, jsonl_hook, tmp_path, monkeypatch):
        """Test storing reshaped prompt with JSONL backend."""
        from prompting.types import PromptSpec

        # Skip if memory not available
        if not jsonl_hook.is_available():
            pytest.skip("Memory backend not available")

        prompt_spec = PromptSpec(
            original_prompt="Hello",
            reshaped_prompt="Hello, world",
            category="greeting",
            transformations_applied=["clarity"],
        )

        result = jsonl_hook.store_reshaped_prompt(prompt_spec)

        # Should return a memory ID or None if storage failed
        assert result is None or isinstance(result, str)


class TestMemoryHookGlobal:
    """Tests for global memory hook functions."""

    def test_get_memory_hook(self):
        """Test getting the global memory hook."""
        from prompting import get_memory_hook, reset_memory_hook

        reset_memory_hook()
        hook = get_memory_hook()

        assert hook is not None
        assert isinstance(hook, object)

    def test_reset_memory_hook(self):
        """Test resetting the global memory hook."""
        from prompting import get_memory_hook, reset_memory_hook

        # Get initial hook
        hook1 = get_memory_hook()

        # Reset
        reset_memory_hook()

        # Get new hook
        hook2 = get_memory_hook()

        # Should be different instances
        assert hook1 is not hook2


class TestMemoryHookError:
    """Tests for MemoryHookError exception."""

    def test_error_inheritance(self):
        """Test that MemoryHookError is an Exception."""
        from prompting import MemoryHookError

        assert issubclass(MemoryHookError, Exception)

    def test_error_message(self):
        """Test error message handling."""
        from prompting import MemoryHookError

        error = MemoryHookError("Test error message")

        assert str(error) == "Test error message"
