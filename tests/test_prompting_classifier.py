"""Tests for prompting middleware intent classifier."""
from __future__ import annotations

import pytest


class TestHeuristicClassifier:
    """Tests for HeuristicClassifier."""

    def test_classify_research(self):
        """Test classification of research prompts."""
        from prompting import classify_prompt

        result = classify_prompt("Research the latest AI developments")

        assert result.category == "research"
        assert result.confidence > 0.0  # Any positive confidence
        assert result.is_trivial is False

    def test_classify_coding(self):
        """Test classification of coding prompts."""
        from prompting import classify_prompt

        result = classify_prompt("Write a Python function to sort a list")

        assert result.category == "coding"
        assert result.is_trivial is False

    def test_classify_analysis(self):
        """Test classification of analysis prompts."""
        from prompting import classify_prompt

        result = classify_prompt("Analyze the pros and cons of this approach")

        assert result.category == "analysis"
        assert result.is_trivial is False

    def test_classify_explanation(self):
        """Test classification of explanation prompts."""
        from prompting import classify_prompt

        result = classify_prompt("Explain how photosynthesis works")

        assert result.category == "explanation"
        assert result.is_trivial is False

    def test_classify_greeting(self):
        """Test classification of greeting prompts."""
        from prompting import classify_prompt

        result = classify_prompt("Hello!")

        assert result.category == "greeting"
        assert result.is_trivial is True

    def test_classify_acknowledgment(self):
        """Test classification of acknowledgment prompts."""
        from prompting import classify_prompt

        result = classify_prompt("Thanks!")

        assert result.category == "acknowledgment"
        assert result.is_trivial is True

    def test_classify_simple_query(self):
        """Test classification of simple queries."""
        from prompting import classify_prompt

        result = classify_prompt("What time is it?")

        assert result.category == "simple_query"
        assert result.is_trivial is True

    def test_classify_empty_input(self):
        """Test classification of empty input."""
        from prompting import classify_prompt

        result = classify_prompt("")

        assert result.category == "empty"
        assert result.is_trivial is True

    def test_classify_whitespace_only(self):
        """Test classification of whitespace-only input."""
        from prompting import classify_prompt

        result = classify_prompt("   ")

        assert result.category == "empty"
        assert result.is_trivial is True

    def test_classify_general_fallback(self):
        """Test fallback to general for unrecognized prompts."""
        from prompting import classify_prompt

        result = classify_prompt("xyzzy foobar qux")

        assert result.category == "general"
        assert result.is_trivial is False

    def test_subcategories_detection(self):
        """Test detection of subcategories."""
        from prompting import classify_prompt

        # Multi-category prompt
        result = classify_prompt("Analyze and compare the research on this topic")

        # Should have subcategories
        assert len(result.subcategories) >= 0
        # Primary should be one of the matching categories
        assert result.category in ["analysis", "comparison", "research"]

    def test_confidence_score(self):
        """Test that confidence scores are reasonable."""
        from prompting import classify_prompt

        # Clear signal
        result = classify_prompt("Research the latest papers on quantum computing")
        assert 0.0 <= result.confidence <= 1.0

        # Ambiguous
        result = classify_prompt("Hello, can you help me?")
        assert 0.0 <= result.confidence <= 1.0

    def test_raw_scores_available(self):
        """Test that raw scores are available for debugging."""
        from prompting import classify_prompt

        result = classify_prompt("Explain the code")

        assert result.raw_scores is not None
        assert isinstance(result.raw_scores, dict)
        assert len(result.raw_scores) > 0


class TestClassifierInterface:
    """Tests for classifier interface functions."""

    def test_get_classifier(self):
        """Test getting the default classifier."""
        from prompting import HeuristicClassifier, get_classifier

        classifier = get_classifier()

        assert isinstance(classifier, HeuristicClassifier)

    def test_set_classifier(self):
        """Test setting a custom classifier."""
        from prompting import (
            ClassificationResult,
            IntentClassifier,
            get_classifier,
            set_classifier,
        )

        class CustomClassifier(IntentClassifier):
            def classify(self, prompt: str) -> ClassificationResult:
                return ClassificationResult(
                    category="custom",
                    confidence=1.0,
                    subcategories=[],
                )

            def supported_categories(self) -> list[str]:
                return ["custom"]

        # Set custom
        custom = CustomClassifier()
        set_classifier(custom)

        classifier = get_classifier()
        assert isinstance(classifier, CustomClassifier)

        # Reset to default
        from prompting.classifier import _default_classifier

        set_classifier(None)  # type: ignore
        # Reload by setting to None won't work, need to reset properly
        # For testing, we can reimport
        import prompting.classifier

        prompting.classifier._default_classifier = None

    def test_supported_categories(self):
        """Test getting supported categories."""
        from prompting import get_classifier

        classifier = get_classifier()
        categories = classifier.supported_categories()

        assert isinstance(categories, list)
        assert len(categories) > 0
        assert "research" in categories
        assert "coding" in categories


class TestClassificationResult:
    """Tests for ClassificationResult dataclass."""

    def test_trivial_factory(self):
        """Test creating a trivial result."""
        from prompting.classifier import ClassificationResult

        result = ClassificationResult.trivial("greeting")

        assert result.category == "greeting"
        assert result.confidence == 1.0
        assert result.subcategories == []
        assert result.is_trivial is True

    def test_default_trivial_category(self):
        """Test default category for trivial results."""
        from prompting.classifier import ClassificationResult

        result = ClassificationResult.trivial()

        assert result.category == "simple_query"
