# Prompting Middleware

The prompting middleware provides prompt reshaping and Chain-of-Verification (CoVe) capabilities to improve prompt quality and response accuracy.

## Overview

This middleware sits between user input and the LLM, providing:

1. **Prompt Reshaping**: Rewrites user input into optimized prompts
2. **Chain-of-Verification (CoVe)**: Multi-step verification of LLM responses
3. **Memory Integration**: Stores artifacts for debugging and tuning
4. **Inspectability**: Optional visibility into reshaped prompts

## Architecture

```
User Input
    │
    ▼
┌─────────────────────┐
│  Intent Classifier  │ ─── Classifies prompt into categories
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│  Prompt Reshaping   │ ─── Rewrites prompt (if enabled for category)
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│    LLM Call         │ ─── Generates draft response
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│  CoVe Pipeline      │ ─── Verifies response (if enabled)
│  ├─ Generate Qs     │
│  ├─ Answer Qs       │
│  └─ Compare         │
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│  Memory Storage     │ ─── Stores artifacts (if enabled)
└─────────────────────┘
    │
    ▼
Final Response + Verified Badge
```

## Current Status

**SCAFFOLD IMPLEMENTATION** - The pipeline is fully structured but does not make actual LLM calls. Currently:
- Prompt reshaping returns input unchanged
- CoVe returns empty verification results
- Memory storage is functional

Future work will add:
- LLM-based prompt reshaping
- Verification question generation
- Claim extraction and verification

## Configuration

Configuration is via environment variables (prefix: `PROMPTING_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMPTING_ENABLE_RESHAPE` | `false` | Enable prompt reshaping |
| `PROMPTING_ENABLE_COVE` | `false` | Enable Chain-of-Verification |
| `PROMPTING_COVE_MIN_QUESTIONS` | `2` | Minimum verification questions |
| `PROMPTING_COVE_MAX_QUESTIONS` | `5` | Maximum verification questions |
| `PROMPTING_ALLOW_INSPECT_RESHAPED` | `false` | Allow users to see reshaped prompt |
| `PROMPTING_RETURN_VERIFIED_BADGE` | `true` | Include verified badge in response |
| `PROMPTING_STORE_DEBUG_ARTIFACTS` | `true` | Store debug artifacts to memory |
| `PROMPTING_RESHAPE_CATEGORIES` | (see below) | Categories triggering reshape |
| `PROMPTING_COVE_CATEGORIES` | (see below) | Categories triggering CoVe |

### Default Categories

**Reshape Categories** (non-trivial prompts):
- research, analysis, coding, planning, creative
- explanation, comparison, recommendation
- problem_solving, summarization

**CoVe Categories** (fact-heavy prompts):
- research, analysis, explanation
- comparison, recommendation, problem_solving

**Excluded Categories** (trivial, bypass pipeline):
- reminder, timer, greeting, acknowledgment, simple_query

## Usage

### Basic Usage

```python
from prompting import PromptingPipeline

# Create pipeline with default config
pipeline = PromptingPipeline()

# Run on user input
result = pipeline.run("What are the main causes of climate change?")

# Access result
print(result.response)      # The final response
print(result.verified)      # True if CoVe passed
print(result.verified_badge)  # "✓ Verified (3/3 checks passed)"
```

### Custom Configuration

```python
from prompting import PromptingPipeline, PromptingConfig

config = PromptingConfig(
    enable_prompt_reshape=True,
    enable_cove=True,
    cove_min_questions=3,
    cove_max_questions=5,
    allow_user_inspect_reshaped_prompt=True,
)

pipeline = PromptingPipeline(config=config)
result = pipeline.run(
    "Explain quantum entanglement",
    include_reshaped_prompt=True,
)

# Access reshaped prompt (if allowed and modified)
if result.reshaped_prompt:
    print(f"Reshaped: {result.reshaped_prompt}")
```

### Convenience Function

```python
from prompting import run_pipeline

result = run_pipeline("How does photosynthesis work?")
```

### Intent Classification

```python
from prompting import classify_prompt

result = classify_prompt("What is the capital of France?")
print(result.category)      # "simple_query"
print(result.is_trivial)    # True
print(result.confidence)    # 0.8
```

## Components

### PromptingConfig

Configuration dataclass with flags and category lists.

```python
from prompting import PromptingConfig

# Load from environment
config = PromptingConfig.from_env()

# Check if category should trigger features
config.should_reshape("research")  # True if reshape enabled
config.should_run_cove("analysis")  # True if CoVe enabled
```

### IntentClassifier

Interface for classifying prompts. Default implementation uses keyword matching.

```python
from prompting import HeuristicClassifier, set_classifier

# Use default
from prompting import classify_prompt
result = classify_prompt("Analyze this data")

# Or set custom classifier
class MyClassifier(IntentClassifier):
    def classify(self, prompt: str) -> ClassificationResult:
        # ML-based classification
        ...

set_classifier(MyClassifier())
```

### MemoryHook

Interface for storing artifacts to Milton's memory system.

```python
from prompting import MemoryHook

hook = MemoryHook()
if hook.is_available():
    # Store reshaped prompt
    hook.store_reshaped_prompt(prompt_spec)
    # Store verification artifacts
    hook.store_verification_artifacts(artifacts)
```

## Types

### PipelineResult

Final result from the pipeline:
- `response`: The final response text
- `verified`: Whether CoVe verification passed
- `verified_badge`: Optional badge string
- `reshaped_prompt`: The reshaped prompt (if allowed/requested)
- `artifacts`: Debug artifacts (if storage enabled)

### PipelineArtifacts

Debug artifacts from a pipeline run:
- `prompt_spec`: Prompt reshaping details
- `draft_response`: Initial LLM response
- `cove_questions`: Verification questions
- `cove_findings`: Verification findings
- `final_response`: Post-verification response

### PromptSpec

Prompt reshaping specification:
- `original_prompt`: Raw user input
- `reshaped_prompt`: Optimized prompt
- `category`: Detected intent category
- `transformations_applied`: List of transformations

## Testing

```bash
# Run prompting tests
pytest tests/test_prompting*.py -v

# Run with coverage
pytest tests/test_prompting*.py --cov=prompting
```

## Future Work

1. **LLM Integration**: Add actual LLM calls for reshaping and verification
2. **Web Search**: Use Perplexity/web search for verification answers
3. **Claim Extraction**: Extract verifiable claims from responses
4. **ML Classifier**: Train a proper intent classifier
5. **Metrics**: Add latency and quality metrics
6. **Caching**: Cache verification results for similar prompts
