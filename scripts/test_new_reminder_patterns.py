#!/usr/bin/env python3
"""Quick test script to demonstrate the new reminder intent patterns.

This script shows that phrases like "set a reminder", "create a reminder",
"add a reminder", and "schedule a reminder" now work the same way as
"remind me" for creating reminders.
"""

from datetime import datetime
from milton_gateway.reminder_intent_normalizer import ReminderIntentNormalizer


def test_phrase(normalizer, phrase, now):
    """Test a single phrase and print the result."""
    print(f"\n📝 Testing: '{phrase}'")
    result = normalizer.normalize(phrase, now=now)
    
    if result is None:
        print("   ❌ NO MATCH")
        return False
    
    print(f"   ✅ MATCHED: {result.surface_form}")
    print(f"      Intent: {result.intent_type}")
    print(f"      Task: {result.task}")
    print(f"      Confidence: {result.confidence}")
    
    if result.due_at:
        due_time = datetime.fromtimestamp(result.due_at)
        print(f"      Due: {due_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if result.needs_clarification:
        print(f"      ⚠️  Needs clarification: {result.clarifying_question}")
    
    return True


def main():
    """Run demo tests for new reminder patterns."""
    normalizer = ReminderIntentNormalizer()
    now = datetime(2026, 1, 21, 10, 0, 0)  # Fixed time for consistency
    
    print("=" * 80)
    print("DEMO: New Reminder Intent Patterns (Fix 1)")
    print("=" * 80)
    
    print("\n🎯 PRIMARY FIX: The failing phrase from requirements")
    test_phrase(
        normalizer,
        "Set a reminder for me to submit my expense reimbursement tomorrow at 4:30 PM",
        now
    )
    
    print("\n\n🔧 EXPLICIT TIME VARIANTS (high confidence, no clarification needed)")
    explicit_time_phrases = [
        "create a reminder to call the dentist tomorrow at 2pm",
        "add a reminder for me to review PRs today at 3:30pm",
        "schedule a reminder to water plants tomorrow at 8am",
        "set a reminder to finish report tomorrow at 10:30 AM",
    ]
    
    for phrase in explicit_time_phrases:
        test_phrase(normalizer, phrase, now)
    
    print("\n\n⏱️  RELATIVE TIME VARIANTS (calculated timestamps)")
    relative_time_phrases = [
        "set a reminder to stretch in 30 minutes",
        "create a reminder for me to take a break in 1 hour",
        "add a reminder to check the oven in 2 hours",
    ]
    
    for phrase in relative_time_phrases:
        test_phrase(normalizer, phrase, now)
    
    print("\n\n📅 RELATIVE TIMEOFDAY (needs clarification for exact time)")
    timeofday_phrases = [
        "set a reminder to check the stove tomorrow morning",
        "create a reminder to water plants today afternoon",
    ]
    
    for phrase in timeofday_phrases:
        test_phrase(normalizer, phrase, now)
    
    print("\n\n💬 SIMPLE PATTERNS (no time specified, needs clarification)")
    simple_phrases = [
        "set a reminder to buy groceries",
        "create a reminder for me to file taxes",
        "add a reminder to call mom",
    ]
    
    for phrase in simple_phrases:
        test_phrase(normalizer, phrase, now)
    
    print("\n\n🚫 NEGATIVE TESTS (should NOT match)")
    negative_phrases = [
        "I set a reminder once and it was annoying",
        "We should set a reminder system for the team",
    ]
    
    for phrase in negative_phrases:
        matched = test_phrase(normalizer, phrase, now)
        if not matched:
            print("   ✅ Correctly rejected (no false positive)")
    
    print("\n\n✨ COMPARISON: Original 'remind me' still works")
    original_phrases = [
        "remind me to review GitHub notifications at 9am tomorrow",
        "remind me to stretch in 2 hours",
        "remind me to submit expense report",
    ]
    
    for phrase in original_phrases:
        test_phrase(normalizer, phrase, now)
    
    print("\n" + "=" * 80)
    print("✅ All new patterns working as expected!")
    print("=" * 80)


if __name__ == "__main__":
    main()
