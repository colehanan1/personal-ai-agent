# Chain-of-Verification (CoVe)

Chain-of-Verification (CoVe) is a multi-step pipeline that verifies factual claims in LLM responses to improve accuracy and reduce hallucinations.

## How CoVe Works

The CoVe pipeline follows these steps:

```
User Input → Draft Response → Generate Questions → Answer Questions → Finalize Response
```

### Step 1: Generate Draft

The LLM generates an initial response to the user's question.

### Step 2: Generate Verification Questions

The pipeline extracts factual claims from the draft and generates verification questions:

```json
{
  "questions": [
    {
      "question_text": "What year was Python released?",
      "target_claim": "Python was released in 1991",
      "source_context": "The language was first released..."
    }
  ]
}
```

Configuration:
- `cove_min_questions`: Minimum questions to generate (default: 2)
- `cove_max_questions`: Maximum questions to generate (default: 5)

### Step 3: Answer Questions Independently

Each verification question is answered independently, without access to the original draft. This prevents the model from simply confirming its own claims.

### Step 4: Finalize Response

The original draft is compared against verification answers. Contradictions are flagged or corrected, and a final verified response is produced.

## Verification Status

Each finding has a verification status:

| Status | Meaning |
|--------|---------|
| `VERIFIED` | Claim confirmed by verification |
| `PARTIALLY_VERIFIED` | Some aspects confirmed, others uncertain |
| `UNVERIFIED` | Could not verify the claim |
| `CONTRADICTED` | Verification contradicts the claim |
| `NOT_APPLICABLE` | Claim cannot be verified (opinions, etc.) |

## Finding Severity

Findings are categorized by severity:

| Severity | Description |
|----------|-------------|
| `INFO` | Informational finding |
| `WARNING` | Potential issue, review recommended |
| `ERROR` | Critical issue, correction needed |

## Verified Badge

When verification passes, a badge is included:

```
Verified (3/3 checks passed)
```

Badge meanings:
- All checks passed: "Verified (N/N checks passed)"
- Some checks failed: "Verified (X/Y checks passed)"
- Verification unavailable: "Verification unavailable"

## When CoVe Runs

### For User Responses

CoVe runs on non-trivial user responses when:
1. `enable_cove_for_responses=true` in config
2. The request category is in `categories_triggering_cove`

Default CoVe categories:
- research, analysis, explanation
- comparison, recommendation, problem_solving

### For Agent Prompts

CoVe ALWAYS runs on agent-facing prompts when using:
- `mode="generate_prompt"`
- `mode="generate_agent_prompt"`

This ensures prompts sent to other agents are verified.

## Configuration

```bash
# Enable CoVe for the pipeline
export PROMPTING_ENABLE_COVE=true

# Enable CoVe for user responses (config-gated)
export PROMPTING_ENABLE_COVE_FOR_RESPONSES=true

# Question bounds
export PROMPTING_COVE_MIN_QUESTIONS=2
export PROMPTING_COVE_MAX_QUESTIONS=5

# Show verified badge
export PROMPTING_RETURN_VERIFIED_BADGE=true

# Categories that trigger CoVe
export PROMPTING_COVE_CATEGORIES="research,analysis,explanation"
```

## Graceful Degradation

If CoVe fails (e.g., LLM unavailable), the pipeline:
1. Logs a warning
2. Returns the draft response unchanged
3. Sets badge to "Verification unavailable"
4. Does not crash the request

## Disabling CoVe for Speed

To disable CoVe for faster responses:

```bash
# Disable CoVe entirely
export PROMPTING_ENABLE_COVE=false
export PROMPTING_ENABLE_COVE_FOR_RESPONSES=false
```

Or in code:

```python
config = PromptingConfig(
    enable_cove=False,
    enable_cove_for_responses=False,
)
```

Note: Agent prompts (`generate_agent_prompt` mode) always run CoVe regardless of these settings.

## Usage Example

```python
from prompting import ChainOfVerification, PromptingConfig

# Create CoVe instance
config = PromptingConfig(
    cove_min_questions=2,
    cove_max_questions=5,
    return_verified_badge=True,
)
cove = ChainOfVerification(config=config)

# Run verification
result = cove.run(
    user_input="What is the capital of France?",
    draft="The capital of France is Paris, founded in ancient times.",
    request_id="req_123",
)

print(result.final_response)
print(result.badge)  # "Verified (2/2 checks passed)"
print(result.questions)  # Verification questions generated
print(result.findings)   # Any issues found
```

## Debug Artifacts

When `store_debug_artifacts=true`, the pipeline stores:

```python
@dataclass
class PipelineArtifacts:
    request_id: str
    timestamp: datetime
    prompt_spec: PromptSpec
    draft_response: str
    cove_questions: list[CoveQuestion]
    cove_findings: list[CoveFinding]
    final_response: str
    metadata: dict
```

These are stored to memory for debugging and tuning.

## Related Documentation

- [Prompting Pipeline](./PROMPTING_PIPELINE.md) - Overall pipeline architecture
- [Inspect Mode](./INSPECT_MODE.md) - Viewing verification details
