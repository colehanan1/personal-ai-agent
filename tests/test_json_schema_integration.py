"""
Tests for JSON schema structured outputs (2025 feature)

Validates:
- Pydantic model definitions
- JSON schema generation
- Response parsing with schemas
- Integration with existing Perplexity client
"""

import pytest
import json
from unittest.mock import Mock, patch

from perplexity_integration import (
    PerplexityPromptBuilder,
    PerplexityAPIClient,
    SearchMode,
)
from perplexity_integration.response_schemas import (
    ResearchResponse,
    SpecificationResponse,
    DocumentationSearchResponse,
    QuickFactResponse,
    Source,
    get_schema_for_prompt_type,
)


class TestResponseSchemas:
    """Test Pydantic response schemas"""

    def test_research_response_schema(self):
        """Test ResearchResponse schema validation"""
        data = {
            "reasoning": "Searched Anthropic docs for Claude best practices",
            "sources": [
                {"id": 1, "title": "Claude Docs", "url": "https://docs.anthropic.com"}
            ],
            "answer": "Best practices include chain-of-thought prompting[1]",
            "confidence": "high",
            "needs_clarification": None,
        }

        response = ResearchResponse.model_validate(data)
        assert response.confidence == "high"
        assert len(response.sources) == 1
        assert response.sources[0].url == "https://docs.anthropic.com"

    def test_specification_response_schema(self):
        """Test SpecificationResponse schema validation"""
        data = {
            "objective": "Add user authentication",
            "context": "Python Flask app",
            "reasoning": "Analyzed Flask-Login documentation",
            "sources": [
                {"id": 1, "title": "Flask-Login Docs", "url": "https://flask-login.readthedocs.io"}
            ],
            "technical_constraints": {
                "language": "Python 3.11+",
                "frameworks": ["Flask 3.0", "Flask-Login"],
            },
            "file_boundaries": ["src/auth.py", "src/models.py"],
            "testing_requirements": {
                "commands": ["pytest tests/test_auth.py"],
                "coverage": "80%",
            },
            "implementation_plan": [
                "Install Flask-Login",
                "Create User model",
                "Add login routes",
            ],
            "deliverables": ["Working authentication system", "Tests"],
            "confidence": "high",
        }

        response = SpecificationResponse.model_validate(data)
        assert response.objective == "Add user authentication"
        assert "Flask 3.0" in response.technical_constraints["frameworks"]
        assert len(response.file_boundaries) == 2

    def test_source_schema(self):
        """Test Source schema validation"""
        source_data = {
            "id": 1,
            "title": "Perplexity API Docs",
            "url": "https://docs.perplexity.ai",
            "relevance": "Official documentation for structured outputs",
        }

        source = Source.model_validate(source_data)
        assert source.id == 1
        assert source.title == "Perplexity API Docs"

    def test_get_schema_for_prompt_type(self):
        """Test schema retrieval by prompt type"""
        assert get_schema_for_prompt_type("research") == ResearchResponse
        assert get_schema_for_prompt_type("specification") == SpecificationResponse
        assert get_schema_for_prompt_type("documentation") == DocumentationSearchResponse
        assert get_schema_for_prompt_type("fact") == QuickFactResponse

        with pytest.raises(ValueError):
            get_schema_for_prompt_type("unknown_type")

    def test_json_schema_generation(self):
        """Test that Pydantic models generate valid JSON schemas"""
        schema = ResearchResponse.model_json_schema()

        assert "properties" in schema
        assert "reasoning" in schema["properties"]
        assert "sources" in schema["properties"]
        assert "answer" in schema["properties"]
        assert "confidence" in schema["properties"]

        # Check that constraints are in schema
        assert schema["properties"]["reasoning"]["maxLength"] == 800
        assert schema["properties"]["answer"]["maxLength"] == 1500

    def test_validation_with_invalid_data(self):
        """Test that validation fails with invalid data"""
        from pydantic import ValidationError

        # Missing required field
        invalid_data = {
            "reasoning": "Some reasoning",
            # missing sources
            "answer": "Some answer",
            "confidence": "high",
        }

        with pytest.raises(ValidationError):
            ResearchResponse.model_validate(invalid_data)

        # Invalid confidence value
        invalid_data = {
            "reasoning": "Some reasoning",
            "sources": [{"id": 1, "title": "Title", "url": "https://example.com"}],
            "answer": "Some answer",
            "confidence": "invalid",  # Should be high/medium/low
        }

        with pytest.raises(ValidationError):
            ResearchResponse.model_validate(invalid_data)


class TestJSONSchemaAPIIntegration:
    """Test JSON schema integration with API client"""

    @patch('requests.Session.post')
    def test_execute_with_json_schema(self, mock_post):
        """Test executing structured prompt with JSON schema"""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "reasoning": "Searched for Claude best practices",
                        "sources": [
                            {"id": 1, "title": "Claude Docs", "url": "https://docs.anthropic.com"}
                        ],
                        "answer": "Use chain-of-thought prompting[1]",
                        "confidence": "high",
                        "needs_clarification": None,
                    })
                },
                "finish_reason": "stop"
            }],
            "model": "sonar-pro",
            "usage": {"total_tokens": 500},
            "citations": ["https://docs.anthropic.com"],
        }
        mock_post.return_value = mock_response

        # Create client and prompt
        client = PerplexityAPIClient(api_key="test-key")
        builder = PerplexityPromptBuilder()

        prompt = builder.build_research_prompt(
            query="What are Claude best practices?",
            context="Milton AI system",
        )

        # Execute with JSON schema
        response = client.execute_structured_prompt(
            prompt,
            response_schema=ResearchResponse,
            use_json_schema=True,
        )

        assert response is not None
        assert response.has_citations
        assert "chain-of-thought" in response.content.lower()
        assert len(response.citations) > 0

    @patch('requests.Session.post')
    def test_json_schema_in_request_payload(self, mock_post):
        """Test that JSON schema is included in API request"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "reasoning": "Test",
                        "sources": [{"id": 1, "title": "T", "url": "https://t.com"}],
                        "answer": "Test answer",
                        "confidence": "high",
                    })
                },
                "finish_reason": "stop"
            }],
            "model": "sonar-pro",
            "usage": {"total_tokens": 100},
        }
        mock_post.return_value = mock_response

        client = PerplexityAPIClient(api_key="test-key")
        builder = PerplexityPromptBuilder()

        prompt = builder.build_research_prompt(
            query="Test query",
            context="Test context",
        )

        client.execute_structured_prompt(
            prompt,
            response_schema=ResearchResponse,
            use_json_schema=True,
        )

        # Verify that response_format was added to payload
        call_args = mock_post.call_args
        payload = call_args[1]['json']

        assert 'response_format' in payload
        assert payload['response_format']['type'] == 'json_schema'
        assert 'json_schema' in payload['response_format']

    @patch('requests.Session.post')
    def test_fallback_to_regular_parsing_on_invalid_json(self, mock_post):
        """Test fallback when JSON parsing fails"""
        # Mock response with invalid JSON
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Not valid JSON content"
                },
                "finish_reason": "stop"
            }],
            "model": "sonar-pro",
            "usage": {"total_tokens": 100},
            "citations": ["https://example.com"],
        }
        mock_post.return_value = mock_response

        client = PerplexityAPIClient(api_key="test-key")
        builder = PerplexityPromptBuilder()

        prompt = builder.build_research_prompt(
            query="Test query",
            context="Test context",
        )

        # Should not crash, should fallback to regular parsing
        response = client.execute_structured_prompt(
            prompt,
            response_schema=ResearchResponse,
            use_json_schema=True,
        )

        assert response is not None
        assert response.content == "Not valid JSON content"


class TestSystemPromptUpdates:
    """Test that system prompts enforce JSON output"""

    def test_research_system_message_has_json_requirement(self):
        """Test that research system message requires JSON output"""
        builder = PerplexityPromptBuilder()
        system_msg = builder.build_system_message("research")

        assert "JSON" in system_msg
        assert "json" in system_msg.lower()
        assert "schema" in system_msg.lower()

    def test_specification_system_message_has_json_requirement(self):
        """Test that specification system message requires JSON output"""
        builder = PerplexityPromptBuilder()
        system_msg = builder.build_system_message("specification")

        assert "JSON" in system_msg
        assert "json" in system_msg.lower()

    def test_system_messages_mention_repository_context(self):
        """Test that system messages reference repository context"""
        builder = PerplexityPromptBuilder()

        research_msg = builder.build_system_message("research")
        spec_msg = builder.build_system_message("specification")

        assert "REPO" in research_msg or "repository" in research_msg.lower()
        assert "REPO" in spec_msg or "repository" in spec_msg.lower()

    def test_system_messages_mention_chain_of_thought(self):
        """Test that system messages include chain-of-thought guidance"""
        builder = PerplexityPromptBuilder()

        research_msg = builder.build_system_message("research")
        spec_msg = builder.build_system_message("specification")

        assert "reasoning" in research_msg.lower() or "chain-of-thought" in research_msg.lower()
        assert "reasoning" in spec_msg.lower() or "chain-of-thought" in spec_msg.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
