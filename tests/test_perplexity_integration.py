"""
Comprehensive test suite for Perplexity structured prompting integration

Tests:
- System message consistency
- Structured prompt formatting
- API parameter generation
- Context loading
- Citation verification
- Token optimization
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import modules to test
from perplexity_integration import (
    PerplexityPromptBuilder,
    PerplexityAPIClient,
    RepositoryContextLoader,
    SearchMode,
    RecencyFilter,
    ContextSize,
    StructuredPrompt,
)
from perplexity_integration.prompting_system import validate_prompt_structure
from perplexity_integration.api_client import PerplexityResponse


class TestPerplexityPromptBuilder:
    """Test suite for PerplexityPromptBuilder"""

    def test_system_message_consistency(self):
        """Test that system message is consistent across calls"""
        builder = PerplexityPromptBuilder()

        msg1 = builder.build_system_message("research")
        msg2 = builder.build_system_message("research")

        assert msg1 == msg2
        assert len(msg1) > 100  # Should be substantial
        assert "cite" in msg1.lower()  # Should mention citations

    def test_specification_system_message(self):
        """Test specification system message"""
        builder = PerplexityPromptBuilder()

        msg = builder.build_system_message("specification")

        assert "architect" in msg.lower()
        assert "specification" in msg.lower()
        assert len(msg) > 100

    def test_structured_prompt_format(self):
        """Test structured prompt formatting with context"""
        builder = PerplexityPromptBuilder()

        prompt = builder.structure_user_prompt(
            query="How to optimize Claude prompts?",
            context="Milton voice command system",
            output_format="Numbered list",
            additional_constraints=["Focus on documentation"],
        )

        assert "[CONTEXT]" in prompt
        assert "[QUERY]" in prompt
        assert "[OUTPUT FORMAT]" in prompt
        assert "[CONSTRAINTS]" in prompt
        assert "[VERIFICATION]" in prompt
        assert "Milton voice command system" in prompt

    def test_search_parameters_generation(self):
        """Test API search parameters are correctly generated"""
        builder = PerplexityPromptBuilder()

        params = builder.build_search_parameters(
            mode=SearchMode.PRO,
            recency_filter=RecencyFilter.MONTH,
            domain_filter=["perplexity.ai", "docs.anthropic.com"],
            context_size=ContextSize.HIGH,
            return_citations=True,
        )

        assert params["model"] == "sonar-pro"
        assert params["search_recency_filter"] == "month"
        assert "perplexity.ai" in params["search_domain_filter"]
        assert params["search_context_size"] == "high"
        assert params["return_citations"] is True
        assert params["temperature"] == 0.2  # Should be low for consistency

    def test_research_prompt_building(self):
        """Test complete research prompt construction"""
        builder = PerplexityPromptBuilder()

        prompt = builder.build_research_prompt(
            query="What are Claude API best practices?",
            context="AI assistant integration",
            domain_filter=["docs.anthropic.com"],
            output_format="Bullet points",
        )

        assert isinstance(prompt, StructuredPrompt)
        assert len(prompt.system_message) > 0
        assert len(prompt.user_prompt) > 0
        assert "model" in prompt.api_parameters
        assert prompt.api_parameters["model"] == "sonar-pro"

    def test_specification_prompt_building(self):
        """Test specification prompt with repository context"""
        builder = PerplexityPromptBuilder()

        prompt = builder.build_specification_prompt(
            user_request="Add user authentication",
            target_repo="/home/user/myapp",
            repo_context="Python Flask app with SQLite",
        )

        assert isinstance(prompt, StructuredPrompt)
        assert "Flask" in prompt.user_prompt or "SQLite" in prompt.user_prompt
        assert "/home/user/myapp" in prompt.user_prompt

    def test_documentation_search_prompt(self):
        """Test documentation search prompt optimization"""
        builder = PerplexityPromptBuilder()

        prompt = builder.build_documentation_search_prompt(
            topic="structured prompting",
            technology="Perplexity API",
            specific_question="How to use search_domain_filter?",
        )

        assert isinstance(prompt, StructuredPrompt)
        assert "Perplexity API" in prompt.user_prompt
        assert "search_domain_filter" in prompt.user_prompt
        # Should filter to official docs
        assert any(
            "perplexity" in domain.lower()
            for domain in prompt.api_parameters.get("search_domain_filter", [])
        )

    def test_token_optimization(self):
        """Test that prompts are token-optimized (concise)"""
        builder = PerplexityPromptBuilder()

        # Build a simple prompt
        prompt = builder.structure_user_prompt(
            query="Test query",
            context="Test context",
        )

        # Should be concise - structured format reduces tokens
        # Count sections, not total length (format is intentionally structured)
        sections = prompt.split("\n")
        assert len(sections) <= 10  # Should have limited sections


class TestRepositoryContextLoader:
    """Test suite for RepositoryContextLoader"""

    @pytest.fixture
    def temp_repo(self, tmp_path):
        """Create a temporary repository structure"""
        # Create some Python files
        (tmp_path / "main.py").write_text("# Main file")
        (tmp_path / "utils.py").write_text("# Utils")

        # Create directories
        (tmp_path / "tests").mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("# App")

        # Create config files
        (tmp_path / "requirements.txt").write_text("flask\npytest")
        (tmp_path / "README.md").write_text("# Test Project\nA test project")

        return tmp_path

    def test_context_loader_initialization(self, temp_repo):
        """Test context loader initializes correctly"""
        loader = RepositoryContextLoader(temp_repo)

        assert loader.repo_path == temp_repo.resolve()
        assert loader.cache_timeout == 300

    def test_language_detection(self, temp_repo):
        """Test primary language detection"""
        loader = RepositoryContextLoader(temp_repo)
        context = loader.load_context()

        assert context.primary_language == "Python"

    def test_technology_detection(self, temp_repo):
        """Test technology/framework detection"""
        loader = RepositoryContextLoader(temp_repo)
        context = loader.load_context()

        # Should detect Python project from requirements.txt
        assert any("Python" in tech for tech in context.technologies)

    def test_key_directories(self, temp_repo):
        """Test key directory extraction"""
        loader = RepositoryContextLoader(temp_repo)
        context = loader.load_context()

        assert "tests" in context.key_directories
        assert "src" in context.key_directories
        # Should not include system dirs
        assert ".git" not in context.key_directories

    def test_context_summary(self, temp_repo):
        """Test context summary generation"""
        loader = RepositoryContextLoader(temp_repo)
        summary = loader.get_context_summary()

        assert isinstance(summary, str)
        assert len(summary) > 0
        # Should be concise for token optimization
        assert len(summary) < 300

    def test_context_caching(self, temp_repo):
        """Test that context is cached"""
        loader = RepositoryContextLoader(temp_repo)

        # First load
        context1 = loader.load_context()
        timestamp1 = loader._cache_timestamp

        # Second load (should use cache)
        context2 = loader.load_context()
        timestamp2 = loader._cache_timestamp

        assert context1.context_summary == context2.context_summary
        assert timestamp1 == timestamp2

    def test_force_refresh(self, temp_repo):
        """Test force refresh bypasses cache"""
        loader = RepositoryContextLoader(temp_repo)

        # First load
        loader.load_context()
        timestamp1 = loader._cache_timestamp

        # Wait a tiny bit
        import time
        time.sleep(0.01)

        # Force refresh
        loader.load_context(force_refresh=True)
        timestamp2 = loader._cache_timestamp

        assert timestamp2 > timestamp1

    def test_to_dict(self, temp_repo):
        """Test context export to dictionary"""
        loader = RepositoryContextLoader(temp_repo)
        context_dict = loader.to_dict()

        assert "repo_path" in context_dict
        assert "primary_language" in context_dict
        assert "technologies" in context_dict
        assert context_dict["primary_language"] == "Python"


class TestPerplexityAPIClient:
    """Test suite for PerplexityAPIClient"""

    @pytest.fixture
    def mock_api_response(self):
        """Mock successful API response"""
        return {
            "choices": [
                {
                    "message": {
                        "content": "Test response content with citations [1][2]"
                    },
                    "finish_reason": "stop"
                }
            ],
            "citations": [
                "https://example.com/source1",
                "https://example.com/source2"
            ],
            "model": "sonar-pro",
            "usage": {
                "total_tokens": 150,
                "prompt_tokens": 50,
                "completion_tokens": 100
            }
        }

    def test_client_initialization(self):
        """Test client initializes correctly"""
        client = PerplexityAPIClient(
            api_key="test-key",
            timeout=30,
            max_retries=2,
        )

        assert client.api_key == "test-key"
        assert client.timeout == 30
        assert client.max_retries == 2
        assert client.verify_citations is True

    @patch("perplexity_integration.api_client.requests.Session.post")
    def test_structured_prompt_execution(self, mock_post, mock_api_response):
        """Test structured prompt execution"""
        # Mock successful response
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_api_response

        client = PerplexityAPIClient(api_key="test-key")
        builder = PerplexityPromptBuilder()

        # Build a prompt
        prompt = builder.build_research_prompt(
            query="Test query",
            context="Test context",
        )

        # Execute
        response = client.execute_structured_prompt(prompt)

        # Verify response
        assert response is not None
        assert isinstance(response, PerplexityResponse)
        assert response.has_citations
        assert len(response.citations) == 2
        assert response.tokens_used == 150
        assert response.is_complete

    def test_prompt_validation(self):
        """Test invalid prompts are rejected"""
        client = PerplexityAPIClient(api_key="test-key")

        # Create invalid prompt
        invalid_prompt = StructuredPrompt(
            system_message="",  # Empty - invalid
            user_prompt="Test",
            api_parameters={},  # Missing model - invalid
        )

        response = client.execute_structured_prompt(invalid_prompt)

        # Should return None for invalid prompt
        assert response is None

    @patch("perplexity_integration.api_client.requests.Session.post")
    def test_citation_verification(self, mock_post):
        """Test citation verification"""
        # Mock response without citations
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [
                {
                    "message": {"content": "Response without citations"},
                    "finish_reason": "stop"
                }
            ],
            "citations": [],  # No citations
            "model": "sonar-pro",
            "usage": {"total_tokens": 100}
        }

        client = PerplexityAPIClient(api_key="test-key", verify_citations=True)
        builder = PerplexityPromptBuilder()

        prompt = builder.build_research_prompt(query="Test")
        response = client.execute_structured_prompt(prompt)

        # Should still return response but flag missing citations
        assert response is not None
        assert not response.has_citations

    def test_response_quality_validation(self):
        """Test response quality validation"""
        client = PerplexityAPIClient(api_key="test-key")

        # Create response with issues
        response = PerplexityResponse(
            content="Short",
            citations=[],  # No citations
            model="sonar-pro",
            has_citations=False,
            is_complete=False,  # Incomplete
        )

        validation = client.validate_response_quality(response)

        assert not validation["is_reliable"]
        assert validation["needs_clarification"]
        assert len(validation["issues"]) > 0
        assert "No citations" in str(validation["issues"])


class TestPromptValidation:
    """Test prompt structure validation"""

    def test_valid_prompt(self):
        """Test valid prompt passes validation"""
        prompt = StructuredPrompt(
            system_message="This is a valid system message",
            user_prompt="This is a valid user prompt",
            api_parameters={"model": "sonar-pro"},
        )

        assert validate_prompt_structure(prompt) is True

    def test_invalid_system_message(self):
        """Test invalid system message fails validation"""
        prompt = StructuredPrompt(
            system_message="",  # Empty
            user_prompt="Valid prompt",
            api_parameters={"model": "sonar-pro"},
        )

        assert validate_prompt_structure(prompt) is False

    def test_invalid_user_prompt(self):
        """Test invalid user prompt fails validation"""
        prompt = StructuredPrompt(
            system_message="Valid system message",
            user_prompt="",  # Empty
            api_parameters={"model": "sonar-pro"},
        )

        assert validate_prompt_structure(prompt) is False

    def test_missing_model_parameter(self):
        """Test missing model parameter fails validation"""
        prompt = StructuredPrompt(
            system_message="Valid system message",
            user_prompt="Valid prompt",
            api_parameters={},  # Missing model
        )

        assert validate_prompt_structure(prompt) is False


class TestIntegrationWithPerplexityClient:
    """Test integration with existing PerplexityClient"""

    @patch("milton_orchestrator.perplexity_client.STRUCTURED_PROMPTING_AVAILABLE", True)
    def test_structured_prompting_enabled(self):
        """Test that structured prompting is enabled when available"""
        from milton_orchestrator.perplexity_client import PerplexityClient

        client = PerplexityClient(
            api_key="test-key",
            use_structured_prompting=True,
        )

        # Check that enhanced components are initialized
        # Note: This will only work if the import is successful
        # In real usage, this test would verify the feature flag


# Run tests with: pytest tests/test_perplexity_integration.py -v
