# Fix 3: LLM-Assisted Intent Classification Fallback - Implementation Summary

## Overview

This document describes the implementation of **Fix 3**, which adds an LLM-assisted intent classification fallback to Milton's action planning pipeline. This enhancement allows Milton to handle natural language variations that fail regex pattern matching, while maintaining strict safety guarantees.

**Status**: ✅ **COMPLETE** - Implementation finished, tested, and verified with 0 regressions

**Test Results**: 
- 30 new tests added in `tests/test_llm_fallback.py` (all passing)
- Full test suite: **1662 passed**, 15 skipped, 0 failures

---

## Problem Statement

The original rule-based action planner uses regex patterns to detect user intents. While effective, it has limitations:

1. **Limited coverage**: Phrases like "Set a reminder for me to..." fail to match when patterns only cover "remind me..."
2. **Brittle patterns**: Adding more regex patterns increases complexity and maintenance burden
3. **False negatives**: Valid user requests return NOOP when they don't match patterns

**Goal**: Add an LLM-powered fallback that catches valid action requests when regex fails, without compromising safety or introducing false positives.

---

## Architecture

### 1. Fallback Trigger Flow

```
User Message
     ↓
extract_action_plan() (regex-based)
     ↓
Returns NOOP?
     ↓
should_use_llm_fallback() (heuristic check)
     ↓
Keywords present? (reminder, goal, schedule, etc.)
     ↓
classify_intent_with_llm() (async LLM call)
     ↓
Safety Gates: confidence ≥ 0.85? no missing fields? intent != "unknown"?
     ↓
convert_classification_to_plan()
     ↓
Execute Action OR Return Clarification
```

### 2. Safety Gates (Multiple Layers)

The fallback includes **four safety gates** to prevent unsafe execution:

#### Gate 1: Heuristic Trigger
- **Function**: `should_use_fallback(text)`
- **Purpose**: Prevent unnecessary LLM calls for generic chat
- **Logic**: Only trigger if text contains action keywords:
  - Reminder words: "remind", "reminder", "schedule"
  - Goal words: "goal", "objective", "target"
  - Memory words: "remember", "save", "store", "keep track"
  - Action verbs: "set", "create", "add", "make"

#### Gate 2: JSON Schema Validation
- **Function**: `_parse_and_validate_classification(response)`
- **Purpose**: Ensure LLM output is well-formed and parseable
- **Checks**:
  - Valid JSON syntax
  - ASCII-only (no Unicode that could bypass validation)
  - Required fields present: `intent_type`, `action`, `payload`, `confidence`, `missing_fields`
  - Correct types and value ranges

#### Gate 3: Confidence Threshold
- **Function**: `should_execute_classification(classification)`
- **Purpose**: Only execute high-confidence classifications
- **Threshold**: `confidence >= 0.85` (configurable constant)
- **Rationale**: Low confidence indicates uncertainty → safer to ask for clarification

#### Gate 4: Completeness Check
- **Function**: `should_execute_classification(classification)`
- **Purpose**: Ensure all required fields are present
- **Checks**:
  - `missing_fields` list is empty
  - `intent_type` is not "unknown"
  - `action` is not "noop"

---

## Implementation Details

### New Module: `milton_gateway/llm_intent_classifier.py`

**Complete standalone module** with the following components:

#### 1. Heuristic Trigger
```python
def should_use_fallback(text: str) -> bool:
    """Check if LLM fallback should be attempted.
    
    Returns True if text contains action-indicating keywords.
    This is a fast heuristic gate before expensive LLM call.
    """
```

**Keywords checked**:
- Reminder: "remind", "reminder", "schedule"
- Goal: "goal", "objective", "target"
- Memory: "remember", "save", "store", "keep track"
- Actions: "set", "create", "add", "make", "help me"

#### 2. LLM Classifier
```python
async def classify_intent_with_llm(
    text: str,
    llm_client: Any,
    now_iso: str,
    timezone: str
) -> Optional[Dict[str, Any]]:
    """Call LLM to classify user intent with strict JSON schema.
    
    Returns:
        Validated classification dict or None if invalid/error
    """
```

**LLM Prompt**: Instructs the model to output **single-line ASCII JSON** with schema:
```json
{
  "intent_type": "reminder"|"goal"|"memory"|"unknown",
  "action": "add"|"list"|"delete"|"noop",
  "payload": {...},
  "confidence": 0.0-1.0,
  "missing_fields": []
}
```

**Validation**: Strict checks on all fields before accepting response.

#### 3. Safety Gate Checker
```python
def should_execute_classification(classification: Dict[str, Any]) -> bool:
    """Check if classification passes safety gates for execution.
    
    Returns True only if:
    - confidence >= 0.85
    - missing_fields is empty
    - intent_type != "unknown"
    - action != "noop"
    """
```

#### 4. Plan Converter
```python
def convert_classification_to_plan(
    classification: Dict[str, Any],
    timezone: str
) -> Dict[str, Any]:
    """Convert LLM classification to action_planner format.
    
    Maps intent_type to action constants:
    - "reminder" → CREATE_REMINDER
    - "goal" → CREATE_GOAL
    - "memory" → CREATE_MEMORY
    """
```

**Adds metadata**:
- `source: "llm_fallback"` (for logging/debugging)
- `confidence: <float>` (from LLM)

---

### Integration Points

#### 1. `milton_gateway/action_planner.py`

**Added function**:
```python
def should_use_llm_fallback(plan: Dict[str, Any], user_text: str) -> bool:
    """Check if LLM fallback should be attempted for this plan.
    
    Returns True if:
    - Plan is NOOP (primary detection failed)
    - Text contains action-indicating keywords
    """
```

**Location**: After line 85 (where `extract_action_plan` returns NOOP)

#### 2. `milton_gateway/server.py`

**Modified**: `chat_completions()` function (lines ~562-650)

**Added logic**:
```python
elif plan.get("action") == "NOOP":
    # Check if LLM fallback should be attempted
    if should_use_llm_fallback(plan, user_message):
        logger.info(f"🔄 Attempting LLM fallback for NOOP case")
        
        try:
            # Call async LLM classifier
            classification = await classify_intent_with_llm(...)
            
            if classification and should_execute_classification(classification):
                # Convert to action plan format
                fallback_plan = convert_classification_to_plan(...)
                
                # Execute the fallback plan
                exec_result = execute_action_plan(...)
                action_context = _build_action_context(fallback_plan, exec_result)
                
                logger.info(f"✅ Fallback action executed: {fallback_plan.get('action')}")
            else:
                # Classification failed safety gates
                logger.info(f"🚫 LLM fallback did not meet safety gates")
                action_context = _build_action_context(plan, exec_result=None)
        
        except Exception as e:
            logger.error(f"LLM fallback error: {e}", exc_info=True)
            # Fall through to normal NOOP handling
```

**Key design decisions**:
- Fallback is **async** (doesn't block the primary planner)
- Errors in fallback **don't crash the request** (graceful degradation)
- Extensive logging for audit trail

---

## Test Coverage

### Test Module: `tests/test_llm_fallback.py`

**30 comprehensive tests** across 6 test classes:

#### 1. `TestFallbackTriggerHeuristic` (5 tests)
- ✅ Triggers on reminder keywords
- ✅ Triggers on goal keywords
- ✅ Triggers on memory keywords
- ✅ Does NOT trigger on generic chat
- ✅ Triggers on imperative action verbs

#### 2. `TestClassificationValidation` (8 tests)
- ✅ Accepts valid reminder classification
- ✅ Accepts valid goal classification
- ✅ Rejects invalid JSON
- ✅ Rejects non-ASCII output
- ✅ Rejects invalid intent_type
- ✅ Rejects invalid action
- ✅ Rejects confidence out of range
- ✅ Handles markdown code blocks

#### 3. `TestSafetyGates` (6 tests)
- ✅ High confidence (≥0.85) passes
- ✅ Low confidence (<0.85) fails
- ✅ Unknown intent fails
- ✅ NOOP action fails
- ✅ Missing required fields fails
- ✅ All gates passing succeeds

#### 4. `TestPlanConversion` (3 tests)
- ✅ Reminder → CREATE_REMINDER
- ✅ Goal → CREATE_GOAL
- ✅ Memory → CREATE_MEMORY

#### 5. `TestLLMClassifierIntegration` (5 tests)
All tests use **mocked LLM responses** for deterministic behavior:
- ✅ Successful reminder classification (high confidence)
- ✅ Low confidence classification (safety gate blocks)
- ✅ Missing fields classification (safety gate blocks)
- ✅ Invalid JSON from LLM (gracefully handled)
- ✅ LLM error handling (gracefully handled)

#### 6. `TestDeterministicBehavior` (3 tests)
- ✅ Heuristic is deterministic (same input → same output)
- ✅ Validation is deterministic
- ✅ Safety gates are deterministic

**Mocking Strategy**:
```python
mock_llm_client = AsyncMock()
mock_llm_client.chat_completion = AsyncMock(return_value={
    "choices": [{
        "message": {
            "content": json.dumps({...})
        }
    }]
})
```

This ensures tests are **hermetic** (no actual LLM calls) and **fast**.

---

## Logging and Observability

The fallback includes extensive logging for debugging and audit:

### Log Levels

1. **INFO**: Normal fallback flow
   ```
   🔄 Attempting LLM fallback for NOOP case
   ✅ LLM fallback succeeded: CREATE_REMINDER
   📋 Fallback plan: original_plan=NOOP, fallback_action=CREATE_REMINDER, confidence=0.95
   ✅ Fallback action executed: CREATE_REMINDER -> success
   ```

2. **WARNING**: Validation failures
   ```
   LLM classifier output contains non-ASCII characters
   LLM classifier output is not valid JSON: <error>
   Invalid intent_type: <value>
   ```

3. **ERROR**: Unexpected failures
   ```
   LLM fallback error: <exception>
   ```

### Log Fields

All fallback executions log:
- `original_plan`: Primary planner result (always NOOP for fallback)
- `fallback_action`: Action from LLM classifier
- `confidence`: LLM confidence score
- `execution_result`: Success/failure status

---

## Safety Analysis

### False Positive Prevention

**Q**: Can the fallback accidentally execute actions for non-action requests?

**A**: No. Multiple safety gates prevent this:

1. **Heuristic Gate**: Only triggers if text contains action keywords
   - Example: "Tell me about reminders" → triggers heuristic
   - But LLM classifier will return `action: "noop"` or `intent_type: "unknown"`
   
2. **LLM Classifier**: Trained to distinguish requests from questions
   - "Set a reminder..." → `action: "add"`
   - "What is a reminder?" → `action: "noop"` or `intent_type: "unknown"`
   
3. **Confidence Gate**: Low confidence blocks execution
   - Uncertain classifications → clarification, not execution

4. **Completeness Gate**: Missing fields block execution
   - "Set a reminder to do something" → missing "when" → clarification

### False Negative Prevention

**Q**: Can the fallback miss valid action requests?

**A**: Rare, but possible:

1. **Heuristic misses**: If text has no keywords
   - Example: "Could you ping me about this later?" 
   - Solution: Expand keyword list iteratively based on logs

2. **LLM misclassifies**: If LLM returns wrong intent
   - Example: LLM returns `intent_type: "unknown"` for valid request
   - Solution: Improve LLM prompt; add few-shot examples

3. **Low confidence**: If LLM is uncertain
   - Example: Ambiguous phrasing → confidence < 0.85
   - Solution: This is **by design** (better to clarify than execute wrong action)

**Mitigation**: Extensive logging allows monitoring of false negatives in production.

---

## Performance Considerations

### Latency Impact

**Before fallback**:
- Regex pattern matching: ~0.1ms (negligible)

**With fallback (on NOOP cases only)**:
- Heuristic check: ~0.1ms (negligible)
- LLM classification: ~500-2000ms (depends on model)
- Safety gates: ~0.5ms (negligible)

**Total added latency**: ~500-2000ms **only for NOOP cases that trigger fallback**

**Optimization**: 
- Fallback only runs when primary planner returns NOOP
- Heuristic gate prevents LLM call for generic chat
- Most requests bypass fallback entirely (use existing patterns)

### Cost Impact

**LLM call cost**: ~$0.001-0.01 per classification (varies by model)

**Frequency**:
- Only on NOOP cases with action keywords
- Estimated: 5-10% of total requests

**Monthly cost estimate** (1000 requests/month):
- Fallback triggers: ~50-100 requests
- Cost: ~$0.05-1.00/month

---

## Example Usage

### Example 1: Successful Fallback

**User message**: "Set a reminder for me to submit my expense report tomorrow at 4:30 PM"

**Flow**:
1. `extract_action_plan()` → NOOP (regex pattern doesn't match)
2. `should_use_llm_fallback()` → True (contains "reminder", "set")
3. `classify_intent_with_llm()` → Returns:
   ```json
   {
     "intent_type": "reminder",
     "action": "add",
     "payload": {
       "title": "submit expense report",
       "when": "tomorrow at 4:30 PM",
       "timezone": "America/Chicago"
     },
     "confidence": 0.95,
     "missing_fields": []
   }
   ```
4. `should_execute_classification()` → True (passes all gates)
5. `convert_classification_to_plan()` → CREATE_REMINDER plan
6. `execute_action_plan()` → Creates reminder
7. Response: "✅ I've set a reminder to submit expense report tomorrow at 4:30 PM."

### Example 2: Safety Gate Blocks Execution

**User message**: "Set a reminder to do something"

**Flow**:
1. `extract_action_plan()` → NOOP
2. `should_use_llm_fallback()` → True
3. `classify_intent_with_llm()` → Returns:
   ```json
   {
     "intent_type": "reminder",
     "action": "add",
     "payload": {
       "title": "do something"
     },
     "confidence": 0.70,
     "missing_fields": ["when"]
   }
   ```
4. `should_execute_classification()` → **False** (confidence < 0.85, missing "when")
5. Response: "I'd be happy to set a reminder. When would you like to be reminded?"

### Example 3: Non-Action Chat

**User message**: "Tell me how reminders work"

**Flow**:
1. `extract_action_plan()` → NOOP
2. `should_use_llm_fallback()` → True (contains "reminder")
3. `classify_intent_with_llm()` → Returns:
   ```json
   {
     "intent_type": "unknown",
     "action": "noop",
     "payload": {},
     "confidence": 0.90,
     "missing_fields": []
   }
   ```
4. `should_execute_classification()` → **False** (intent="unknown", action="noop")
5. Response: "Reminders allow you to..." (standard LLM chat response)

---

## Future Enhancements

### 1. Expand Intent Types

**Current**: Reminders, goals, memory
**Future**: 
- Calendar events
- Task management
- Search queries
- Notifications

**Implementation**: Add intent types to `CLASSIFIER_SCHEMA`

### 2. Few-Shot Learning

**Current**: Zero-shot prompt
**Future**: Add example classifications to prompt

**Example**:
```python
Examples:
- "Set a reminder to call mom tomorrow at 3pm" → {"intent_type": "reminder", ...}
- "What time is my next meeting?" → {"intent_type": "unknown", "action": "noop", ...}
```

### 3. Confidence Tuning

**Current**: Fixed threshold (0.85)
**Future**: Dynamic threshold based on:
- Intent type (reminders require higher confidence than queries)
- User history (trusted users get lower threshold)
- Risk assessment (destructive actions require higher confidence)

### 4. Feedback Loop

**Current**: No learning from user corrections
**Future**: Store misclassifications and retrain

**Implementation**:
- Log fallback predictions
- Capture user corrections ("Actually, I meant...")
- Use logged data to improve prompts or fine-tune model

---

## Rollout and Monitoring

### Rollout Strategy

**Phase 1: Shadow Mode** (Recommended)
- Run fallback but don't execute
- Log what fallback would have done
- Compare to user's actual intent (manual review)
- Duration: 1-2 weeks

**Phase 2: Gradual Rollout**
- Enable fallback for 10% of users
- Monitor for false positives/negatives
- Increase to 50%, then 100%
- Duration: 2-4 weeks

**Phase 3: Full Deployment**
- Enable for all users
- Continuous monitoring

### Monitoring Metrics

**Key metrics to track**:

1. **Fallback Trigger Rate**
   - % of NOOP cases that trigger fallback
   - Target: 20-40% (indicates heuristic is selective)

2. **Safety Gate Block Rate**
   - % of classifications blocked by safety gates
   - Target: 10-30% (indicates gates are working)

3. **Execution Success Rate**
   - % of fallback executions that succeed
   - Target: >95%

4. **User Corrections**
   - % of fallback actions that user corrects/undoes
   - Target: <5%

5. **Latency**
   - P50, P95, P99 latency for fallback cases
   - Target: P95 < 2s

**Alerting thresholds**:
- Fallback trigger rate > 60% (heuristic too broad)
- Safety gate block rate > 50% (LLM confidence too low)
- User corrections > 10% (false positives)

---

## Conclusion

**Fix 3 is complete and production-ready**:

✅ **Robust implementation** with 4 safety gates  
✅ **Comprehensive testing** (30 tests, 100% pass rate)  
✅ **Zero regressions** (1662 tests pass)  
✅ **Extensive logging** for observability  
✅ **Graceful degradation** on errors  
✅ **Deterministic tests** with mocked LLM responses  

**Key achievements**:
1. Enables natural language variations beyond regex patterns
2. Maintains safety with multiple validation layers
3. Adds minimal latency (only on NOOP cases)
4. Fully tested and documented

**Next steps**:
- Deploy in shadow mode for 1-2 weeks
- Monitor metrics (trigger rate, safety gates, user corrections)
- Gradually roll out to production
- Iterate based on production logs

---

## Files Changed

### New Files
- `milton_gateway/llm_intent_classifier.py` (340 lines)
- `tests/test_llm_fallback.py` (490 lines)
- `FIX3_LLM_FALLBACK_SUMMARY.md` (this file)

### Modified Files
- `milton_gateway/action_planner.py`
  - Added `should_use_llm_fallback()` function
  - Updated docstring for `extract_action_plan()`

- `milton_gateway/server.py`
  - Modified NOOP handling to call fallback (lines ~562-650)
  - Added async LLM classification flow
  - Added safety gate checks
  - Added extensive logging

### Test Results
```bash
$ python -m pytest tests/test_llm_fallback.py -v
================================================== 30 passed in 0.03s ==================================================

$ python -m pytest -q
=========== 1662 passed, 15 skipped, 2 warnings in 79.08s (0:01:19) ============
```

**Zero regressions. All systems operational.** 🚀
