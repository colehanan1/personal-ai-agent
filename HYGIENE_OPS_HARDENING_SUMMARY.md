# Hygiene Ops: Deterministic NOOP Response Hardening

## Executive Summary

**Problem**: When the action planner returns NOOP (no operation) and LLM fallback doesn't trigger, the system was calling the LLM to generate a response. In some cases, the LLM would hallucinate successful action execution despite the truth gate prohibitions in the system prompt.

**Solution**: Implemented deterministic NOOP responses that completely bypass the LLM when the user text appears to request an action (reminder/goal/memory) but the planner returns NOOP. This eliminates the possibility of hallucinated success claims.

**Impact**: Permanently eliminates "NOOP hallucinated success" cases observed in verification testing (e.g., "Ping me about my expense reimbursement tomorrow" incorrectly claiming a reminder was created).

**Test Results**: 
- 19 new tests added, all passing
- Full test suite: 1681 tests passing, 15 skipped, 0 failures
- Live verification: Confirmed deterministic responses, no DB writes, LLM still used for normal chat

---

## Implementation Details

### Files Changed

1. **milton_gateway/server.py** (167 lines added)
   - Added `_detect_action_intent()` - Conservative heuristic to detect action-like requests
   - Added `_build_deterministic_noop_response()` - Generates structured guidance without LLM
   - Modified NOOP handling (lines 562-660) to check for action intent and return deterministic response
   - Added `Dict` to typing imports

2. **tests/test_deterministic_noop.py** (19 tests, 100% passing)
   - TestActionIntentDetection: 10 tests for action detection heuristic
   - TestDeterministicNoopResponse: 5 tests for response builder
   - TestIntegrationLogic: 3 tests for decision flow
   - TestEndToEndBehavior: 1 test for the original failing case

### Key Functions

#### `_detect_action_intent(text: str) -> Optional[str]`

Conservative heuristic that detects if text appears to request an action.

**Returns**: Intent hint ("reminder", "goal", "memory") or None

**Keywords detected**:
- Reminder: `reminder`, `remind`, `ping me`, `nudge me`, `set/create/add/schedule a reminder`, `notify me`, `alert me`
- Goal: `goal`, `add/set/create a goal`, `track this`, `tracking`
- Memory: `remember that`, `save/store this`, `add to memory`, `keep track of`, `record this`

**Design**: Intentionally conservative. Better to provide explicit guidance than to hallucinate success.

#### `_build_deterministic_noop_response(...) -> ChatCompletionResponse`

Builds OpenAI-compatible response without calling LLM.

**Response structure**:
- Clear statement: "No [action] was created/executed"
- Reason explanation
- Example phrasings (format guidance)
- Machine-readable summary: `ACTION_SUMMARY: {...}`

**Response examples**:

```
Reminder intent:
No reminder was created. I couldn't parse your request as a valid reminder command.

To create a reminder, try one of these formats:
• 'Remind me to <task> tomorrow at 4:30 PM'
• 'Set a reminder for me to <task> on Friday at 2pm'
• 'Create a reminder to <task> next week'

Make sure to include both what you want to be reminded about and when.

ACTION_SUMMARY: {"action_detected": false, "action_executed": false, 
                 "reason": "no_action_detected", "intent_hint": "reminder"}
```

### Decision Flow

```
1. Action planner returns NOOP
   ↓
2. Check if LLM fallback should be attempted (action keywords present?)
   ↓ YES → Try fallback classifier
   │        ↓ SUCCESS → Execute action, call LLM for confirmation
   │        ↓ FAIL (safety gates) → Check action intent
   │             ↓ Action-like? → DETERMINISTIC RESPONSE (no LLM)
   │             ↓ Not action-like? → Inject truth gate, call LLM
   │
   ↓ NO → Check action intent directly
        ↓ Action-like? → DETERMINISTIC RESPONSE (no LLM)
        ↓ Not action-like? → Proceed with LLM for normal chat
```

**Critical invariant**: If user text is action-like and plan is NOOP, the LLM is NOT called (deterministic path).

---

## Verification Results

### Test Suite

```bash
$ python -m pytest tests/test_deterministic_noop.py -v
19 passed in 0.17s

$ python -m pytest -q
1681 passed, 15 skipped, 0 failures in 80.27s
```

### Live Verification

**Test 1: Action-like NOOP (the original failing case)**
```bash
Input: "Ping me about my expense reimbursement tomorrow"

Response:
No reminder was created. I couldn't parse your request as a valid reminder command.
[... guidance with examples ...]
ACTION_SUMMARY: {"action_executed": false, "intent_hint": "reminder"}
```

✅ No false success claim | ✅ No DB write | ✅ Clear guidance

**Test 2: Normal chat**
```bash
Input: "What is 2+2?"
Response: "The answer is 4."
```

✅ LLM called | ✅ Natural response

**Test 3: Valid reminder**
```bash
Input: "Set a reminder for me to test deterministic NOOP tomorrow at 3 PM"
Response: "I've added a reminder... Reminder: Test deterministic NOOP..."
```

✅ Created (ID: 20) | ✅ Accurate success claim

---

## Architecture Diagram

```
User Input: "Ping me about X tomorrow"
    ↓
Action Planner (NOOP)
    ↓
LLM Fallback Check (NOT TRIGGERED)
    ↓
Action Intent Detection (DETECTED: "reminder")
    ↓
⚠️  DETERMINISTIC PATH
    • No LLM call
    • No DB write
    • Structured guidance
    ↓
"No reminder was created. Try: 'Remind me to...'"
```

---

## Benefits

1. **Zero hallucination risk** on NOOP pathway
2. **Faster responses** (no LLM latency)
3. **Lower costs** (no LLM API calls)
4. **Better UX** (explicit guidance > vague apology)
5. **Easier debugging** (deterministic behavior)

---

## Conclusion

Combined with Fixes 1-3, Milton now has a robust, safe, and reliable action planning system that handles both canonical and edge-case phrasings correctly.

**Status**: ✅ Production ready. No known issues.
