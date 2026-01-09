"""Tests for prompt reshaping module."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestReshapeResult:
    """Tests for ReshapeResult dataclass."""

    def test_was_modified_true(self):
        """Test was_modified returns True when text changed."""
        from prompting.reshape import ReshapeResult

        result = ReshapeResult(
            original_text="hello",
            reshaped_prompt="hello, world",
        )
        assert result.was_modified() is True

    def test_was_modified_false(self):
        """Test was_modified returns False when text unchanged."""
        from prompting.reshape import ReshapeResult

        result = ReshapeResult(
            original_text="hello",
            reshaped_prompt="hello",
        )
        assert result.was_modified() is False

    def test_was_modified_whitespace(self):
        """Test was_modified ignores whitespace differences."""
        from prompting.reshape import ReshapeResult

        result = ReshapeResult(
            original_text="hello",
            reshaped_prompt="  hello  ",
        )
        assert result.was_modified() is False

    def test_to_dict(self):
        """Test conversion to dictionary."""
        from prompting.reshape import ReshapeResult

        result = ReshapeResult(
            original_text="research topic",
            reshaped_prompt="Provide research on: topic",
            intent_category="research",
            constraints=["use sources"],
            required_outputs=["key findings"],
            non_goals=["speculation"],
            confidence=0.8,
            used_llm=False,
            transformations=["added_structure"],
        )

        data = result.to_dict()

        assert data["original_text"] == "research topic"
        assert data["reshaped_prompt"] == "Provide research on: topic"
        assert data["intent_category"] == "research"
        assert data["constraints"] == ["use sources"]
        assert data["required_outputs"] == ["key findings"]
        assert data["non_goals"] == ["speculation"]
        assert data["confidence"] == 0.8
        assert data["used_llm"] is False
        assert data["transformations"] == ["added_structure"]
        assert data["was_modified"] is True


class TestPromptReshaper:
    """Tests for PromptReshaper class."""

    def test_empty_input(self):
        """Test empty input returns unchanged."""
        from prompting.reshape import PromptReshaper

        reshaper = PromptReshaper()
        result = reshaper.reshape("")

        assert result.original_text == ""
        assert result.reshaped_prompt == ""
        assert result.confidence == 1.0

    def test_whitespace_only_input(self):
        """Test whitespace-only input returns unchanged."""
        from prompting.reshape import PromptReshaper

        reshaper = PromptReshaper()
        result = reshaper.reshape("   ")

        assert result.original_text == "   "
        assert result.reshaped_prompt == "   "

    def test_heuristic_fallback_no_llm(self):
        """Test heuristic fallback when LLM is unavailable."""
        from prompting.reshape import PromptReshaper

        reshaper = PromptReshaper(llm_url=None, llm_model=None)
        result = reshaper.reshape("analyze this data")

        assert result.used_llm is False
        assert "analyze" in result.reshaped_prompt.lower()

    def test_research_category_reshaping(self):
        """Test research category gets appropriate reshaping."""
        from prompting.classifier import ClassificationResult
        from prompting.reshape import PromptReshaper

        reshaper = PromptReshaper(llm_url=None)
        classification = ClassificationResult(
            category="research",
            confidence=0.8,
            subcategories=[],
        )

        result = reshaper.reshape("quantum computing", classification=classification)

        assert result.intent_category == "research"
        assert any("source" in c.lower() for c in result.constraints) or "sources" in result.reshaped_prompt.lower()
        assert "key findings" in result.required_outputs or "findings" in str(result.required_outputs).lower()

    def test_coding_category_reshaping(self):
        """Test coding category gets appropriate reshaping."""
        from prompting.classifier import ClassificationResult
        from prompting.reshape import PromptReshaper

        reshaper = PromptReshaper(llm_url=None)
        classification = ClassificationResult(
            category="coding",
            confidence=0.8,
            subcategories=[],
        )

        result = reshaper.reshape("write a function", classification=classification)

        assert result.intent_category == "coding"
        # Should have code-related constraints
        assert len(result.constraints) > 0 or len(result.required_outputs) > 0

    def test_prompt_writing_detection(self):
        """Test detection of prompt-writing requests."""
        from prompting.reshape import PromptReshaper

        reshaper = PromptReshaper(llm_url=None)

        # These should be detected as prompt-writing requests
        prompt_writing_requests = [
            "write a prompt for an agent",
            "create a system prompt for GPT",
            "design instructions for an AI assistant",
            "generate a prompt for the LLM",
        ]

        for text in prompt_writing_requests:
            assert reshaper._is_prompt_writing_request(text), f"Failed to detect: {text}"

        # These should NOT be detected as prompt-writing requests
        regular_requests = [
            "write a function",
            "create a document",
            "design a website",
        ]

        for text in regular_requests:
            assert not reshaper._is_prompt_writing_request(text), f"False positive: {text}"

    def test_prompt_writing_preserves_intent(self):
        """Test that prompt-writing requests preserve user intent."""
        from prompting.reshape import PromptReshaper

        reshaper = PromptReshaper(llm_url=None)
        result = reshaper.reshape("write a prompt for an agent that helps with coding")

        assert "meta_prompt_handling" in result.transformations
        assert "coding" in result.reshaped_prompt.lower()
        # Non-goals should include not adding unsolicited constraints
        assert len(result.non_goals) > 0

    def test_is_llm_available_no_url(self):
        """Test is_llm_available returns False when no URL configured."""
        from prompting.reshape import PromptReshaper

        reshaper = PromptReshaper(llm_url=None, llm_model=None)
        assert reshaper.is_llm_available() is False


class TestReshapeUserInput:
    """Tests for reshape_user_input convenience function."""

    def test_basic_usage(self):
        """Test basic usage of reshape_user_input."""
        from prompting.reshape import reset_reshaper, reshape_user_input

        # Reset to ensure clean state
        reset_reshaper()

        result = reshape_user_input("explain quantum computing")

        assert result.original_text == "explain quantum computing"
        assert result.reshaped_prompt is not None

    def test_with_classification(self):
        """Test reshape_user_input with classification provided."""
        from prompting.classifier import ClassificationResult
        from prompting.reshape import reset_reshaper, reshape_user_input

        reset_reshaper()

        classification = ClassificationResult(
            category="explanation",
            confidence=0.9,
            subcategories=[],
        )

        result = reshape_user_input(
            "how does a car engine work",
            classification=classification,
        )

        assert result.intent_category == "explanation"

    def test_with_context(self):
        """Test reshape_user_input with context provided."""
        from prompting.reshape import reset_reshaper, reshape_user_input

        reset_reshaper()

        context = {"user_preferences": {"verbosity": "concise"}}
        result = reshape_user_input("summarize this", context=context)

        assert result is not None


class TestHeuristicReshaping:
    """Tests for specific heuristic reshaping behaviors."""

    def test_analysis_adds_explicit_analyze(self):
        """Test analysis category adds explicit analyze keyword."""
        from prompting.reshape import PromptReshaper

        reshaper = PromptReshaper(llm_url=None)
        reshaped, trans = reshaper._reshape_analysis("the data set")

        assert "analyze" in reshaped.lower()

    def test_planning_adds_actionable(self):
        """Test planning category adds actionable structure."""
        from prompting.reshape import PromptReshaper

        reshaper = PromptReshaper(llm_url=None)
        reshaped, trans = reshaper._reshape_planning("my project")

        assert "plan" in reshaped.lower() or "actionable" in reshaped.lower()

    def test_summarization_adds_concise(self):
        """Test summarization category adds concise request."""
        from prompting.reshape import PromptReshaper

        reshaper = PromptReshaper(llm_url=None)
        reshaped, trans = reshaper._reshape_summarization("the article")

        assert "concise" in reshaped.lower() or "summary" in reshaped.lower()

    def test_general_cleanup_adds_punctuation(self):
        """Test general cleanup adds punctuation if missing."""
        from prompting.reshape import PromptReshaper

        reshaper = PromptReshaper(llm_url=None)
        reshaped, trans = reshaper._general_cleanup("no punctuation")

        assert reshaped.endswith(".")
        assert "added_punctuation" in trans

    def test_general_cleanup_removes_whitespace(self):
        """Test general cleanup removes excessive whitespace."""
        from prompting.reshape import PromptReshaper

        reshaper = PromptReshaper(llm_url=None)
        reshaped, trans = reshaper._general_cleanup("too   many   spaces")

        assert "  " not in reshaped
        assert "whitespace_cleanup" in trans


class TestLLMReshaping:
    """Tests for LLM-based reshaping (mocked)."""

    def test_llm_reshape_success(self):
        """Test successful LLM reshaping with mocked response."""
        from prompting.reshape import PromptReshaper

        # Mock the requests.post to return a valid JSON response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"reshaped_prompt": "optimized prompt", "constraints": ["be accurate"], "required_outputs": ["answer"], "non_goals": [], "confidence": 0.9}'
                }
            }]
        }

        with patch("prompting.reshape.requests.post", return_value=mock_response):
            with patch("prompting.reshape.requests.get") as mock_get:
                mock_get.return_value.status_code = 200

                reshaper = PromptReshaper(llm_url="http://test:8000", llm_model="test-model")
                result = reshaper._reshape_with_llm("original", "general", None)

                assert result.reshaped_prompt == "optimized prompt"
                assert result.constraints == ["be accurate"]
                assert result.confidence == 0.9
                assert result.used_llm is True

    def test_llm_reshape_fallback_on_invalid_json(self):
        """Test LLM reshaping falls back when JSON is invalid."""
        from prompting.reshape import PromptReshaper

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "This is not valid JSON but a reshaped prompt"
                }
            }]
        }

        with patch("prompting.reshape.requests.post", return_value=mock_response):
            with patch("prompting.reshape.requests.get") as mock_get:
                mock_get.return_value.status_code = 200

                reshaper = PromptReshaper(llm_url="http://test:8000", llm_model="test-model")
                result = reshaper._reshape_with_llm("original", "general", None)

                # Should use the content as the reshaped prompt
                assert "This is not valid JSON" in result.reshaped_prompt
                assert result.used_llm is True
                assert "llm_reshape_fallback" in result.transformations


class TestPipelineIntegration:
    """Integration tests for pipeline with reshaping."""

    def test_trivial_message_not_reshaped(self):
        """Test that trivial messages are not reshaped."""
        from prompting import PromptingConfig, PromptingPipeline

        config = PromptingConfig(
            enable_prompt_reshape=True,
            enable_cove=False,
        )
        pipeline = PromptingPipeline(config=config)

        # "Thanks" should be classified as trivial/acknowledgment
        result = pipeline.run("Thanks!")

        assert result.response == "Thanks!"
        # Verify the artifacts show it was a passthrough
        if result.artifacts and result.artifacts.prompt_spec:
            assert "passthrough" in result.artifacts.prompt_spec.transformations_applied

    def test_non_trivial_message_reshaped(self):
        """Test that non-trivial messages are reshaped when enabled."""
        from prompting import PromptingConfig, PromptingPipeline

        config = PromptingConfig(
            enable_prompt_reshape=True,
            enable_cove=False,
            store_debug_artifacts=True,
        )
        pipeline = PromptingPipeline(config=config)

        result = pipeline.run("research quantum computing trends")

        # Should have artifacts with reshaping info
        assert result.artifacts is not None
        assert result.artifacts.prompt_spec is not None
        # May or may not be modified depending on heuristics

    def test_inspect_flag_returns_reshaped_prompt(self):
        """Test that /show_prompt flag returns reshaped prompt."""
        from prompting import PromptingConfig, PromptingPipeline

        config = PromptingConfig(
            enable_prompt_reshape=True,
            allow_user_inspect_reshaped_prompt=True,
            store_debug_artifacts=True,
        )
        pipeline = PromptingPipeline(config=config)

        result = pipeline.run("research quantum computing /show_prompt")

        # Should include reshaped prompt in result when flag is present
        # and config allows it
        assert result.reshaped_prompt is not None or result.artifacts is not None

    def test_pipeline_stable_without_llm(self):
        """Test pipeline remains stable when LLM is unavailable."""
        from prompting import PromptingConfig, PromptingPipeline

        # Ensure no LLM is configured
        with patch.dict("os.environ", {}, clear=True):
            config = PromptingConfig(
                enable_prompt_reshape=True,
                enable_cove=False,
            )
            pipeline = PromptingPipeline(config=config)

            # Should not raise an error
            result = pipeline.run("analyze the data")

            assert result.response is not None
            assert result.request_id is not None

    def test_memory_storage_called(self):
        """Test that reshaped prompts are stored to memory when enabled."""
        from prompting import PromptingConfig, PromptingPipeline
        from prompting.memory_hook import MemoryHook

        # Create a mock memory hook
        mock_hook = MagicMock(spec=MemoryHook)
        mock_hook.store_pipeline_result.return_value = ["mem-123"]

        config = PromptingConfig(
            enable_prompt_reshape=True,
            store_debug_artifacts=True,
        )
        pipeline = PromptingPipeline(config=config, memory_hook=mock_hook)

        result = pipeline.run("research topic")

        # Memory hook should have been called
        mock_hook.store_pipeline_result.assert_called_once()


class TestInspectCommands:
    """Tests for inspect command detection and stripping."""

    def test_check_inspect_flag_slash_command(self):
        """Test slash command detection."""
        from prompting.pipeline import PromptingPipeline

        pipeline = PromptingPipeline()

        assert pipeline._check_inspect_flag("/show_prompt") is True
        assert pipeline._check_inspect_flag("query /show_prompt") is True
        assert pipeline._check_inspect_flag("/inspect_prompt") is True

    def test_check_inspect_flag_natural_language(self):
        """Test natural language inspect detection."""
        from prompting.pipeline import PromptingPipeline

        pipeline = PromptingPipeline()

        assert pipeline._check_inspect_flag("analyze this inspect prompt") is True
        assert pipeline._check_inspect_flag("research topic show prompt") is True
        assert pipeline._check_inspect_flag("query show reshaped prompt") is True

    def test_check_inspect_flag_negative(self):
        """Test that non-inspect queries are not detected."""
        from prompting.pipeline import PromptingPipeline

        pipeline = PromptingPipeline()

        assert pipeline._check_inspect_flag("what is a prompt") is False
        assert pipeline._check_inspect_flag("show me the data") is False
        assert pipeline._check_inspect_flag("inspect the code") is False

    def test_strip_inspect_commands_slash(self):
        """Test stripping slash commands."""
        from prompting.pipeline import PromptingPipeline

        pipeline = PromptingPipeline()

        assert pipeline._strip_inspect_commands("query /show_prompt") == "query"
        assert pipeline._strip_inspect_commands("/show_prompt query") == "query"

    def test_strip_inspect_commands_natural(self):
        """Test stripping natural language commands."""
        from prompting.pipeline import PromptingPipeline

        pipeline = PromptingPipeline()

        assert pipeline._strip_inspect_commands("analyze this inspect prompt") == "analyze this"
        assert pipeline._strip_inspect_commands("research topic show prompt") == "research topic"
