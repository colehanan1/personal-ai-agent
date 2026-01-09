# Prompting Pipeline

The prompting pipeline is Milton's middleware for improving prompt quality and response accuracy through prompt reshaping and Chain-of-Verification (CoVe).

## Overview

The pipeline supports four modes:

| Mode | Description | Use Case |
|------|-------------|----------|
| `reshape_only` | Reshapes the prompt without generating a response | Default mode for most requests |
| `full_answer` | Generates a draft answer, then runs CoVe verification | User question answering |
| `generate_prompt` | Reshapes and ALWAYS CoVe-verifies the prompt itself | Prompt generation |
| `generate_agent_prompt` | Quality checks + reshaping + ALWAYS CoVe | Agent-facing prompt generation |

## Prompt Reshaping

Reshaping transforms user input into an optimized prompt for the LLM. This includes:

- **Clarifying intent**: Making implicit requirements explicit
- **Adding structure**: Organizing the request with clear sections
- **Including constraints**: Specifying boundaries and requirements
- **Defining outputs**: Stating expected response format

### Categories Triggering Reshaping

By default, these categories trigger reshaping:
- research, analysis, coding, planning
- creative, explanation, comparison
- recommendation, problem_solving, summarization

Trivial categories are excluded:
- reminder, timer, greeting, acknowledgment, simple_query

### Configuration

```bash
# Enable/disable reshaping
export PROMPTING_ENABLE_RESHAPE=true

# Customize categories
export PROMPTING_RESHAPE_CATEGORIES="research,analysis,coding"
```

## Quality Checks (Agent Prompts)

When generating agent-facing prompts (`generate_agent_prompt` mode), the pipeline enforces quality requirements:

### Required Elements

1. **Inputs/Outputs**: Explicit description of expected inputs and outputs
2. **Constraints**: Rules, limitations, and requirements
3. **Testing Instructions**: How to verify correctness

### Revision Loop

If quality checks fail, the pipeline automatically revises the prompt (max 2 retries):

```
Prompt → Quality Check → FAIL → Revise → Quality Check → FAIL → Revise → Quality Check
```

Heuristic additions are appended for missing elements:
- Missing inputs/outputs → Adds "Expected Inputs/Outputs" section
- Missing constraints → Adds "Constraints" section
- Missing testing → Adds "Testing Requirements" section

## Integration Points

### NEXUS Agent

The prompting pipeline is integrated into NEXUS's `process_message()`:
- Reshapes incoming user messages
- Runs CoVe on non-trivial responses (when `enable_cove_for_responses=true`)
- Returns `verified_badge` in the Response

### Orchestrator

The orchestrator uses the pipeline for agent prompt generation:
- Runs `generate_agent_prompt` mode before building Claude/Codex prompts
- Applies quality checks and CoVe verification
- Stores artifacts to memory

## Pipeline Result

The pipeline returns a `PipelineResult` containing:

```python
@dataclass
class PipelineResult:
    response: str              # Final processed response
    verified: bool             # Whether verification passed
    verified_badge: str        # e.g., "Verified (3/3 checks passed)"
    reshaped_prompt: str       # Inspect output (if requested)
    artifacts: PipelineArtifacts  # Debug artifacts
    request_id: str            # Unique request identifier
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMPTING_ENABLE_RESHAPE` | `false` | Enable prompt reshaping |
| `PROMPTING_ENABLE_COVE` | `false` | Enable Chain-of-Verification |
| `PROMPTING_ENABLE_COVE_FOR_RESPONSES` | `false` | CoVe for user responses |
| `PROMPTING_RETURN_VERIFIED_BADGE` | `true` | Include verified badge |
| `PROMPTING_STORE_DEBUG_ARTIFACTS` | `true` | Store debug artifacts |
| `PROMPTING_RESHAPE_CATEGORIES` | See above | Categories triggering reshape |
| `PROMPTING_COVE_CATEGORIES` | See above | Categories triggering CoVe |

## Usage Example

```python
from prompting import PromptingPipeline, PromptingConfig

# Create pipeline with custom config
config = PromptingConfig(
    enable_prompt_reshape=True,
    enable_cove=True,
)
pipeline = PromptingPipeline(config=config)

# Run with different modes
result = pipeline.run("Explain quantum computing", mode="full_answer")
print(result.response)
print(result.verified_badge)  # "Verified (3/3 checks passed)"

# Agent prompt generation
result = pipeline.run(
    "Create a coding task for parsing JSON",
    mode="generate_agent_prompt"
)
print(result.response)  # Quality-checked, CoVe-verified prompt
```

## Related Documentation

- [CoVe Verification](./COVE_VERIFICATION.md) - How Chain-of-Verification works
- [Inspect Mode](./INSPECT_MODE.md) - Viewing reshaped prompts and verification details
