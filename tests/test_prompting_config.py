"""Tests for prompting middleware configuration."""
from __future__ import annotations

import pytest


class TestPromptingConfig:
    """Tests for PromptingConfig dataclass."""

    def test_default_values(self):
        """Test that defaults preserve current behavior (disabled)."""
        from prompting import PromptingConfig

        config = PromptingConfig()

        # Pipeline should be disabled by default
        assert config.enable_prompt_reshape is False
        assert config.enable_cove is False

        # Other defaults
        assert config.cove_min_questions == 2
        assert config.cove_max_questions == 5
        assert config.allow_user_inspect_reshaped_prompt is False
        assert config.return_verified_badge is True
        assert config.store_debug_artifacts is True

    def test_from_env_defaults(self, monkeypatch):
        """Test loading config from environment with defaults."""
        import os

        from prompting import PromptingConfig

        # Clear any existing env vars
        for key in list(os.environ.keys()):
            if key.startswith("PROMPTING_"):
                monkeypatch.delenv(key, raising=False)

        config = PromptingConfig.from_env()

        # Should match dataclass defaults
        assert config.enable_prompt_reshape is False
        assert config.enable_cove is False

    def test_from_env_enabled(self, monkeypatch):
        """Test loading config with pipeline enabled."""
        from prompting import PromptingConfig

        monkeypatch.setenv("PROMPTING_ENABLE_RESHAPE", "true")
        monkeypatch.setenv("PROMPTING_ENABLE_COVE", "1")
        monkeypatch.setenv("PROMPTING_COVE_MIN_QUESTIONS", "3")
        monkeypatch.setenv("PROMPTING_COVE_MAX_QUESTIONS", "7")

        config = PromptingConfig.from_env()

        assert config.enable_prompt_reshape is True
        assert config.enable_cove is True
        assert config.cove_min_questions == 3
        assert config.cove_max_questions == 7

    def test_from_env_custom_categories(self, monkeypatch):
        """Test loading custom categories from environment."""
        from prompting import PromptingConfig

        monkeypatch.setenv("PROMPTING_RESHAPE_CATEGORIES", "research,coding,custom")
        monkeypatch.setenv("PROMPTING_COVE_CATEGORIES", "research,analysis")

        config = PromptingConfig.from_env()

        assert config.categories_triggering_reshape == ["research", "coding", "custom"]
        assert config.categories_triggering_cove == ["research", "analysis"]

    def test_validate_valid_config(self):
        """Test validation passes for valid config."""
        from prompting import PromptingConfig

        config = PromptingConfig()
        errors = config.validate()

        assert errors == []

    def test_validate_invalid_questions(self):
        """Test validation catches invalid question counts."""
        from prompting import PromptingConfig

        config = PromptingConfig(
            cove_min_questions=0,
            cove_max_questions=1,
        )
        errors = config.validate()

        assert "cove_min_questions must be at least 1" in errors

    def test_validate_max_less_than_min(self):
        """Test validation catches max < min questions."""
        from prompting import PromptingConfig

        config = PromptingConfig(
            cove_min_questions=5,
            cove_max_questions=3,
        )
        errors = config.validate()

        assert "cove_max_questions must be >= cove_min_questions" in errors

    def test_validate_excessive_questions(self):
        """Test validation warns about excessive question count."""
        from prompting import PromptingConfig

        config = PromptingConfig(
            cove_max_questions=15,
        )
        errors = config.validate()

        assert "cove_max_questions should not exceed 10" in errors

    def test_should_reshape_disabled(self):
        """Test should_reshape returns False when disabled."""
        from prompting import PromptingConfig

        config = PromptingConfig(enable_prompt_reshape=False)

        assert config.should_reshape("research") is False
        assert config.should_reshape("coding") is False

    def test_should_reshape_enabled(self):
        """Test should_reshape returns True for matching categories."""
        from prompting import PromptingConfig

        config = PromptingConfig(enable_prompt_reshape=True)

        assert config.should_reshape("research") is True
        assert config.should_reshape("coding") is True
        # Not in default list
        assert config.should_reshape("unknown_category") is False

    def test_should_run_cove_disabled(self):
        """Test should_run_cove returns False when disabled."""
        from prompting import PromptingConfig

        config = PromptingConfig(enable_cove=False)

        assert config.should_run_cove("research") is False
        assert config.should_run_cove("analysis") is False

    def test_should_run_cove_enabled(self):
        """Test should_run_cove returns True for matching categories."""
        from prompting import PromptingConfig

        config = PromptingConfig(enable_cove=True)

        assert config.should_run_cove("research") is True
        assert config.should_run_cove("analysis") is True
        # Not in CoVe categories (coding is not fact-heavy)
        assert config.should_run_cove("coding") is False

    def test_case_insensitive_categories(self):
        """Test category matching is case-insensitive."""
        from prompting import PromptingConfig

        config = PromptingConfig(
            enable_prompt_reshape=True,
            enable_cove=True,
        )

        assert config.should_reshape("RESEARCH") is True
        assert config.should_reshape("Research") is True
        assert config.should_run_cove("ANALYSIS") is True
