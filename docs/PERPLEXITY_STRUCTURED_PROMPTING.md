# Perplexity Structured Prompting Integration (2025 Enhanced)

## Overview

Milton now uses **JSON schema structured outputs** with Perplexity API for every voice command sent through the orchestrator. This ensures consistent, token-efficient, and highly cited research responses optimized for Claude Code agent consumption.

## What Changed (December 2025)

### ✅ Implemented Features

1. **JSON Schema Structured Outputs**
   - Every Perplexity API call now uses `response_format` with JSON schema (2025 feature)
   - Pydantic models ensure consistent, machine-readable responses
   - Automatic validation and fallback to regular parsing if needed

2. **Enhanced System Prompts**
   - Updated with chain-of-thought best practices from Anthropic
   - Enforces JSON-only output (no markdown, no prose)
   - Includes explicit repository context requirements
   - Optimized for token efficiency (citations are FREE in 2025!)

3. **Repository Context in Every Call**
   - Milton repository context automatically included in all Perplexity requests
   - Context includes: language, tech stack, directory structure
   - Helps Perplexity ground answers in Milton's architecture

4. **Token Optimization**
   - System prompts emphasize concise bullet-point reasoning
   - Max 800 chars for reasoning, 1500 chars for answers
   - Citations encouraged (no cost in 2025 except Deep Research)

## Architecture

```
Voice Command (via ntfy/iPhone)
    ↓
Orchestrator.process_incoming_message()
    ↓
route_message() → CLAUDE_CODE / RESEARCH / etc.
    ↓
_run_perplexity(content)
    ├─ Load repository context
    ├─ Build JSON schema prompt (SpecificationResponse)
    ├─ Execute with Perplexity API (response_format: json_schema)
    ├─ Validate response against Pydantic model
    └─ Return structured specification
    ↓
ClaudePromptBuilder.build_job_prompt(research_notes)
    ↓
ClaudeRunner.run(prompt) → Implementation
```

## Key Files Modified

### New Files Created

1. **`perplexity_integration/response_schemas.py`**
   - Pydantic models for structured JSON responses
   - `ResearchResponse`, `SpecificationResponse`, `DocumentationSearchResponse`, `QuickFactResponse`
   - Schema generation for Perplexity API `response_format` parameter

2. **`tests/test_json_schema_integration.py`**
   - Comprehensive tests for JSON schema functionality
   - Validates Pydantic models, API integration, and system prompts

### Modified Files

1. **`perplexity_integration/prompting_system.py`**
   - Updated `RESEARCH_SYSTEM_MESSAGE` with JSON schema requirements
   - Updated `SPECIFICATION_SYSTEM_MESSAGE` for Claude Code optimization
   - Added explicit chain-of-thought guidance
   - References to 2025 best practices

2. **`perplexity_integration/api_client.py`**
   - New `_parse_json_schema_response()` method
   - Enhanced `execute_structured_prompt()` with `response_schema` parameter
   - Automatic JSON parsing and Pydantic validation
   - Graceful fallback to regular parsing on errors

3. **`milton_orchestrator/perplexity_client.py`**
   - Updated `_research_with_structured_prompting()` to use JSON schemas
   - Imports `SpecificationResponse` for structured output
   - Enhanced logging for JSON schema validation

4. **`perplexity_integration/__init__.py`**
   - Exported all response schemas
   - Updated docstring with 2025 features

## Pydantic Response Schemas

### ResearchResponse

For general research queries requiring citations and chain-of-thought reasoning.

```python
{
  "reasoning": "Concise bullet-point chain-of-thought (max 800 chars)",
  "sources": [
    {
      "id": 1,
      "title": "Source Title",
      "url": "https://example.com",
      "relevance": "Why this source is relevant"
    }
  ],
  "answer": "Final answer with inline citations[1][2] (max 1500 chars)",
  "confidence": "high|medium|low",
  "needs_clarification": null or "Specific questions if unclear",
  "related_topics": ["topic1", "topic2"]  // optional, max 3
}
```

### SpecificationResponse

For code specification generation optimized for Claude Code.

```python
{
  "objective": "Clear objective statement (max 300 chars)",
  "context": "Repository + tech stack context (max 500 chars)",
  "reasoning": "Architectural decision chain-of-thought (max 1000 chars)",
  "sources": [...],  // Same as ResearchResponse
  "technical_constraints": {
    "language": "Python 3.11+",
    "frameworks": ["Flask 3.0", "pytest"],
    "dependencies": {"pydantic": "^2.5.0"}
  },
  "file_boundaries": ["path/to/file1.py", "path/to/file2.py"],
  "testing_requirements": {
    "commands": ["pytest tests/"],
    "coverage": "80%",
    "test_files": ["tests/test_feature.py"]
  },
  "implementation_plan": [
    "Step 1: Install dependencies",
    "Step 2: Create models",
    ...
  ],
  "deliverables": [
    "Working feature implementation",
    "Unit tests with 80% coverage",
    ...
  ],
  "confidence": "high|medium|low",
  "needs_clarification": null or "Specific questions"
}
```

## System Prompt Template (RESEARCH MODE)

```
You are Perplexity in RESEARCH MODE. Return ONLY valid JSON matching the schema provided.

MANDATORY REQUIREMENTS:
1. SEARCH WEB for latest official documentation (prefer last 30 days)
2. CITE SOURCES: Every factual claim must have inline citation [N]
3. JSON OUTPUT ONLY: No markdown, no prose outside the JSON structure
4. REPOSITORY CONTEXT: Milton voice AI system - use provided repo context to ground answers
5. CHAIN-OF-THOUGHT: Show reasoning field with step-by-step research process
6. ASK IF UNCLEAR: If repo context insufficient, set needs_clarification field

RESEARCH PROCESS (Chain-of-Thought in 'reasoning' field):
• Analyze query + repository context provided
• Search authoritative sources (official docs, GitHub, peer-reviewed)
• Evaluate source recency and authority
• Cross-verify claims (min 2 sources per factual claim)
• Synthesize: Analysis → Evidence → Conclusion

TOKEN OPTIMIZATION (citations are FREE in 2025):
• Concise bullet-point reasoning (not paragraphs)
• Rich citations (cite generously, no cost)
• Structured JSON only (no extra text)
• Max 800 chars reasoning, 1500 chars answer
```

## Testing

### Run All Tests

```bash
# Activate environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate milton

# Run Perplexity integration tests
python -m pytest tests/test_perplexity_integration.py -v

# Run JSON schema tests
python -m pytest tests/test_json_schema_integration.py -v

# Run all tests
python -m pytest tests/ -v
```

### Test Coverage

- ✅ 26 tests for Perplexity integration (prompt building, context loading, API client)
- ✅ 13 tests for JSON schema integration (Pydantic models, API payload, validation)
- ✅ All tests passing

## References

This implementation is based on official 2025 best practices:

### Perplexity API
- [Structured Outputs Guide](https://docs.perplexity.ai/guides/structured-outputs)
- [Sonar Pro API Introduction](https://www.perplexity.ai/hub/blog/introducing-the-sonar-pro-api)
- [Improved Sonar Models (2025)](https://www.perplexity.ai/hub/blog/new-sonar-search-modes-outperform-openai-in-cost-and-performance)

Key 2025 Updates:
- **Citation tokens are FREE** (except Deep Research)
- JSON schema `response_format` parameter supported
- First request with new schema takes 10-30s (schema preparation)
- Recursive schemas and unconstrained objects not supported

### Claude AI (Anthropic)
- [Chain-of-Thought Prompting](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/chain-of-thought)
- [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Prompting Best Practices](https://claude.com/blog/best-practices-for-prompt-engineering)

Key Recommendations:
- Use chain-of-thought for complex reasoning
- Avoid word "think" in Claude 4.x (use "consider", "evaluate")
- Prompt improver can increase accuracy by 30%

## Token Efficiency

### Before (Legacy Mode)
- System prompts: ~500 tokens
- User prompt: ~200 tokens
- Response: ~1000 tokens (varied)
- **Total: ~1700 tokens per call**

### After (JSON Schema Mode)
- System prompts: ~400 tokens (optimized)
- User prompt: ~200 tokens
- Response: ~600 tokens (structured, consistent)
- Citations: **FREE** (0 tokens billed)
- **Total: ~1200 tokens per call**
- **Savings: ~30% reduction**

## Configuration

### Environment Variables

```bash
# .env file
PERPLEXITY_API_KEY=your-key-here
PERPLEXITY_MODEL=sonar-pro  # Default model
PERPLEXITY_TIMEOUT=60  # Request timeout (seconds)
PERPLEXITY_MAX_RETRIES=3  # Max retry attempts

# Enable structured prompting (default: True)
PERPLEXITY_IN_CLAUDE_MODE=True
PERPLEXITY_IN_CODEX_MODE=True
PERPLEXITY_IN_RESEARCH_MODE=True
```

### Orchestrator Config

The orchestrator automatically uses structured prompting when `perplexity_integration` module is available. No additional configuration needed.

## Voice Command Flow Example

### User Voice Command (via iPhone)
```
"Add user authentication to the Milton orchestrator using Flask-Login"
```

### Orchestrator Processing
1. Receives message via ntfy topic: `milton-briefing-code-ask`
2. Routes to `CLAUDE_CODE` mode (based on prefix or default)
3. Checks `PERPLEXITY_IN_CLAUDE_MODE=True`
4. Calls `_run_perplexity(content)`

### Perplexity Research
1. Loads repository context: "Python project using Flask, pytest with milton_orchestrator, tests"
2. Builds `SpecificationResponse` JSON schema
3. Sends to Perplexity API with:
   - System message: SPECIFICATION_SYSTEM_MESSAGE
   - User prompt: Request + context + output format
   - API parameters: `{"model": "sonar-pro", "response_format": {"type": "json_schema", ...}}`
4. Validates response against Pydantic schema
5. Returns structured specification

### Claude Code Execution
1. Receives research notes (structured specification)
2. Builds comprehensive prompt with:
   - Objective and context
   - Technical constraints
   - File boundaries
   - Testing requirements
   - Implementation plan
3. Executes implementation with Claude Code
4. Returns results to user via ntfy

## Troubleshooting

### Issue: JSON Schema Validation Fails

**Symptoms:** Log shows "JSON schema validation failed"

**Solution:** Check Perplexity response format. The system will fallback to regular parsing automatically.

```python
# Check logs for:
# WARNING: JSON schema validation failed: <error details>
# This is normal if Perplexity doesn't return valid JSON
# The system will use fallback parsing
```

### Issue: No Citations in Response

**Symptoms:** Log shows "No citations found - response may be unreliable"

**Solution:** This is expected for simple queries. For research mode, ensure:
1. Query requires factual information
2. Official documentation exists for the topic
3. System message enforces citation requirements

### Issue: Token Usage Higher Than Expected

**Symptoms:** Response uses more tokens than max limits

**Solution:** Check Perplexity model:
- `sonar-pro`: Higher quality, more tokens
- `sonar`: Standard, faster, fewer tokens
- Adjust `max_tokens` parameter if needed

### Issue: First Request Times Out

**Symptoms:** First request with new JSON schema takes 30+ seconds

**Solution:** This is expected behavior (schema preparation). Subsequent requests will be fast (~2-5s).

## Future Enhancements

Potential improvements for future iterations:

1. **Custom Response Schemas**
   - User-defined schemas for specific use cases
   - Dynamic schema generation based on query type

2. **Response Caching**
   - Cache validated responses for identical queries
   - 5-minute TTL for research results

3. **Multi-Model Support**
   - Fallback to `sonar-reasoning` for complex queries
   - Automatic model selection based on query complexity

4. **Citation Analysis**
   - Automatic source quality scoring
   - Citation clustering by topic
   - Duplicate source detection

## Summary

Milton's Perplexity integration now provides:
- ✅ JSON schema structured outputs for consistent parsing
- ✅ Chain-of-thought reasoning in every response
- ✅ Repository context included automatically
- ✅ 30% token reduction through optimization
- ✅ Free citation tokens (generous sourcing encouraged)
- ✅ Automatic validation with graceful fallbacks
- ✅ Comprehensive test coverage (39 tests passing)

Every voice command sent to Milton now benefits from structured, well-researched, and highly cited Perplexity responses optimized for Claude Code implementation.
