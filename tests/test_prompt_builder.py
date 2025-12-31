"""Tests for prompt builder"""

import pytest
from pathlib import Path
from milton_orchestrator.prompt_builder import (
    ClaudePromptBuilder,
    extract_command_type,
)


class TestExtractCommandType:
    """Tests for command type extraction"""

    def test_code_prefix(self):
        cmd_type, content = extract_command_type("CODE: implement new feature")
        assert cmd_type == "CODE"
        assert content == "implement new feature"

    def test_research_prefix(self):
        cmd_type, content = extract_command_type("RESEARCH: how does auth work?")
        assert cmd_type == "RESEARCH"
        assert content == "how does auth work?"

    def test_lowercase_code_prefix(self):
        cmd_type, content = extract_command_type("code: fix bug")
        assert cmd_type == "CODE"
        assert content == "fix bug"

    def test_no_prefix_defaults_to_code(self):
        cmd_type, content = extract_command_type("just do something")
        assert cmd_type == "CODE"
        assert content == "just do something"

    def test_whitespace_handling(self):
        cmd_type, content = extract_command_type("  CODE:   spaced content  ")
        assert cmd_type == "CODE"
        assert content == "spaced content"


class TestClaudePromptBuilder:
    """Tests for Claude prompt builder"""

    @pytest.fixture
    def builder(self, tmp_path):
        return ClaudePromptBuilder(tmp_path)

    def test_build_job_prompt_basic(self, builder):
        prompt = builder.build_job_prompt("Add a login feature")

        assert "Code Implementation Request" in prompt
        assert "Add a login feature" in prompt
        assert "Implementation Requirements" in prompt
        assert "Testing" in prompt
        assert "IMPLEMENTATION SUMMARY" in prompt

    def test_build_job_prompt_with_research(self, builder):
        research = "Research notes about authentication patterns"
        prompt = builder.build_job_prompt(
            "Add auth",
            research_notes=research,
        )

        assert "Research & Specification" in prompt
        assert research in prompt

    def test_build_job_prompt_without_research(self, builder):
        prompt = builder.build_job_prompt("Add feature")

        assert "Research & Specification" not in prompt

    def test_build_job_prompt_includes_repo_path(self, builder):
        prompt = builder.build_job_prompt("Do something")

        assert str(builder.target_repo) in prompt

    def test_build_research_only_prompt(self, builder):
        prompt = builder.build_research_only_prompt("How does X work?")

        assert "Research Request" in prompt
        assert "How does X work?" in prompt
        assert "without making any code changes" in prompt

    def test_prompt_structure(self, builder):
        prompt = builder.build_job_prompt("Test request")

        # Check for key sections
        required_sections = [
            "Context",
            "Implementation Requirements",
            "Code Quality",
            "Testing",
            "Security",
            "Implementation Plan",
            "Required Deliverables",
            "Final Report Format",
        ]

        for section in required_sections:
            assert section in prompt, f"Missing section: {section}"

    def test_prompt_includes_security_guidance(self, builder):
        prompt = builder.build_job_prompt("Add feature")

        assert "Never commit secrets" in prompt
        assert "environment variables" in prompt
        assert "Validate inputs" in prompt
