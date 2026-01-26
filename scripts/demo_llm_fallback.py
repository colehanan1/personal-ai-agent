#!/usr/bin/env python3
"""Demo script for Fix 3: LLM-Assisted Intent Classification Fallback.

This script demonstrates:
1. Heuristic trigger for fallback
2. LLM classification with strict schema
3. Safety gates preventing unsafe execution
4. Conversion to action plan format

Run with: python scripts/demo_llm_fallback.py
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from milton_gateway.llm_intent_classifier import (
    should_use_fallback,
    should_execute_classification,
    convert_classification_to_plan,
    MIN_CONFIDENCE_THRESHOLD,
    _parse_and_validate_classification,
)


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80 + "\n")


def print_section(title, content):
    """Print a formatted section."""
    print(f"📋 {title}")
    print("-" * 80)
    print(content)
    print()


def demo_heuristic_trigger():
    """Demo: Heuristic trigger decides if fallback should be attempted."""
    print_header("Demo 1: Heuristic Trigger")
    
    test_cases = [
        ("Set a reminder for me to submit expense report", True, "Contains 'reminder' keyword"),
        ("Create a goal to finish the project", True, "Contains 'goal' keyword"),
        ("Remember my WiFi password is ABC123", True, "Contains 'remember' keyword"),
        ("What's the weather like today?", False, "Generic chat - no action keywords"),
        ("Tell me a joke", False, "Generic chat - no action keywords"),
        ("I set a reminder once and it was annoying", True, "Contains 'reminder' but likely not an action"),
    ]
    
    for text, expected, reason in test_cases:
        result = should_use_fallback(text)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{text}'")
        print(f"   → Trigger: {result} (Expected: {expected})")
        print(f"   → Reason: {reason}\n")


def demo_json_validation():
    """Demo: JSON validation catches malformed LLM outputs."""
    print_header("Demo 2: JSON Schema Validation")
    
    test_cases = [
        (
            "Valid reminder classification",
            json.dumps({
                "intent_type": "reminder",
                "action": "add",
                "payload": {"title": "call dentist", "when": "tomorrow at 9am", "timezone": "America/Chicago"},
                "confidence": 0.95,
                "missing_fields": []
            }),
            True
        ),
        (
            "Invalid intent_type",
            json.dumps({
                "intent_type": "invalid_type",
                "action": "add",
                "payload": {},
                "confidence": 0.95,
                "missing_fields": []
            }),
            False
        ),
        (
            "Invalid JSON syntax",
            "This is not JSON",
            False
        ),
        (
            "Confidence out of range",
            json.dumps({
                "intent_type": "reminder",
                "action": "add",
                "payload": {},
                "confidence": 1.5,  # Invalid
                "missing_fields": []
            }),
            False
        ),
    ]
    
    for name, json_str, expected in test_cases:
        result = _parse_and_validate_classification(json_str)
        is_valid = result is not None
        status = "✅" if is_valid == expected else "❌"
        print(f"{status} {name}")
        print(f"   → Valid: {is_valid} (Expected: {expected})")
        if result:
            print(f"   → Parsed: intent={result['intent_type']}, action={result['action']}, conf={result['confidence']}")
        print()


def demo_safety_gates():
    """Demo: Safety gates prevent unsafe execution."""
    print_header("Demo 3: Safety Gates")
    
    test_cases = [
        (
            "High confidence, complete fields",
            {
                "intent_type": "reminder",
                "action": "add",
                "confidence": 0.95,
                "missing_fields": []
            },
            True,
            "All gates pass"
        ),
        (
            "Low confidence (< 0.85)",
            {
                "intent_type": "reminder",
                "action": "add",
                "confidence": 0.70,
                "missing_fields": []
            },
            False,
            f"Confidence {0.70} < {MIN_CONFIDENCE_THRESHOLD}"
        ),
        (
            "Unknown intent",
            {
                "intent_type": "unknown",
                "action": "add",
                "confidence": 0.95,
                "missing_fields": []
            },
            False,
            "Intent type is 'unknown'"
        ),
        (
            "NOOP action",
            {
                "intent_type": "reminder",
                "action": "noop",
                "confidence": 0.95,
                "missing_fields": []
            },
            False,
            "Action is 'noop'"
        ),
        (
            "Missing required fields",
            {
                "intent_type": "reminder",
                "action": "add",
                "confidence": 0.95,
                "missing_fields": ["when"]
            },
            False,
            "Missing field: 'when'"
        ),
    ]
    
    for name, classification, expected, reason in test_cases:
        result = should_execute_classification(classification)
        status = "✅" if result == expected else "❌"
        print(f"{status} {name}")
        print(f"   → Should execute: {result} (Expected: {expected})")
        print(f"   → Reason: {reason}\n")


def demo_plan_conversion():
    """Demo: Convert LLM classification to action plan format."""
    print_header("Demo 4: Plan Conversion")
    
    test_cases = [
        (
            "Reminder classification",
            {
                "intent_type": "reminder",
                "action": "add",
                "payload": {
                    "title": "call dentist",
                    "when": "tomorrow at 9am"
                },
                "confidence": 0.95,
                "missing_fields": []
            },
            "CREATE_REMINDER"
        ),
        (
            "Goal classification",
            {
                "intent_type": "goal",
                "action": "add",
                "payload": {
                    "title": "finish project",
                    "due": "this week"
                },
                "confidence": 0.90,
                "missing_fields": []
            },
            "CREATE_GOAL"
        ),
        (
            "Memory classification",
            {
                "intent_type": "memory",
                "action": "add",
                "payload": {
                    "key": "wifi",
                    "value": "MyPassword123"
                },
                "confidence": 0.92,
                "missing_fields": []
            },
            "CREATE_MEMORY"
        ),
    ]
    
    for name, classification, expected_action in test_cases:
        plan = convert_classification_to_plan(classification, "America/Chicago")
        status = "✅" if plan["action"] == expected_action else "❌"
        print(f"{status} {name}")
        print(f"   → Action: {plan['action']} (Expected: {expected_action})")
        print(f"   → Confidence: {plan['confidence']}")
        print(f"   → Source: {plan['source']}")
        print(f"   → Payload: {json.dumps(plan['payload'], indent=6)}\n")


def demo_end_to_end():
    """Demo: End-to-end flow from text to plan."""
    print_header("Demo 5: End-to-End Flow")
    
    # Scenario: User text that would fail regex but succeeds with fallback
    user_text = "Set a reminder for me to submit my expense report tomorrow at 4:30 PM"
    
    print(f"📝 User text: '{user_text}'\n")
    
    # Step 1: Check if fallback should trigger
    print("Step 1: Check heuristic trigger")
    should_trigger = should_use_fallback(user_text)
    print(f"   → Should trigger fallback: {should_trigger}")
    if not should_trigger:
        print("   → Would stop here (no fallback)")
        return
    print()
    
    # Step 2: Simulate LLM classification
    print("Step 2: LLM classifies intent (mocked)")
    mock_llm_response = {
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
    print(f"   → LLM classification:")
    print(json.dumps(mock_llm_response, indent=6))
    print()
    
    # Step 3: Validate against schema
    print("Step 3: Validate JSON schema")
    json_str = json.dumps(mock_llm_response)
    classification = _parse_and_validate_classification(json_str)
    print(f"   → Validation: {'✅ Passed' if classification else '❌ Failed'}")
    if not classification:
        print("   → Would stop here (invalid response)")
        return
    print()
    
    # Step 4: Check safety gates
    print("Step 4: Check safety gates")
    can_execute = should_execute_classification(classification)
    print(f"   → Confidence: {classification['confidence']} (threshold: {MIN_CONFIDENCE_THRESHOLD})")
    print(f"   → Missing fields: {classification['missing_fields'] or 'None'}")
    print(f"   → Intent type: {classification['intent_type']}")
    print(f"   → Action: {classification['action']}")
    print(f"   → Can execute: {'✅ Yes' if can_execute else '❌ No'}")
    if not can_execute:
        print("   → Would stop here (safety gates blocked)")
        return
    print()
    
    # Step 5: Convert to action plan
    print("Step 5: Convert to action plan")
    plan = convert_classification_to_plan(classification, "America/Chicago")
    print(f"   → Plan action: {plan['action']}")
    print(f"   → Plan payload:")
    print(json.dumps(plan['payload'], indent=6))
    print(f"   → Plan source: {plan['source']}")
    print()
    
    # Step 6: Would execute
    print("Step 6: Execute action")
    print(f"   → Would call execute_action_plan({plan['action']}, ...)")
    print(f"   → Would create reminder: '{plan['payload']['title']}'")
    print(f"   → Would schedule for: {plan['payload']['when']}")
    print()
    
    print("✅ End-to-end flow complete!")


def main():
    """Run all demos."""
    print("\n" + "🚀" * 40)
    print("   Fix 3: LLM-Assisted Intent Classification Fallback - Demo")
    print("🚀" * 40)
    
    demo_heuristic_trigger()
    demo_json_validation()
    demo_safety_gates()
    demo_plan_conversion()
    demo_end_to_end()
    
    print("\n" + "=" * 80)
    print("  All demos complete!")
    print("  See tests/test_llm_fallback.py for comprehensive test suite.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
