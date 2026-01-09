"""
Lightweight intent/category classifier for the prompting middleware.

Provides an interface for classifying user prompts into categories
that determine whether reshaping and/or CoVe should be applied.

The default implementation uses simple heuristics (keyword matching)
with no ML dependencies. Can be extended with ML-based classifiers.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ClassificationResult:
    """
    Result of classifying a user prompt.

    Attributes:
        category: Primary category of the prompt.
        confidence: Confidence score (0.0-1.0) in the classification.
        subcategories: Optional list of secondary categories.
        is_trivial: Whether this is a trivial/simple request.
        raw_scores: Raw scores for each category (for debugging).
    """

    category: str
    confidence: float
    subcategories: list[str]
    is_trivial: bool = False
    raw_scores: Optional[dict[str, float]] = None

    @classmethod
    def trivial(cls, category: str = "simple_query") -> "ClassificationResult":
        """Create a result for a trivial request."""
        return cls(
            category=category,
            confidence=1.0,
            subcategories=[],
            is_trivial=True,
        )


class IntentClassifier(ABC):
    """
    Abstract base class for intent classifiers.

    Implementations should classify user prompts into categories
    that determine pipeline behavior (reshaping, CoVe, etc.).
    """

    @abstractmethod
    def classify(self, prompt: str) -> ClassificationResult:
        """
        Classify a user prompt into a category.

        Args:
            prompt: The raw user input.

        Returns:
            ClassificationResult with category and metadata.
        """
        pass

    @abstractmethod
    def supported_categories(self) -> list[str]:
        """
        Return list of categories this classifier can produce.

        Returns:
            List of category names.
        """
        pass


# Keyword patterns for heuristic classification
CATEGORY_PATTERNS: dict[str, list[str]] = {
    "research": [
        r"\b(research|study|investigate|explore|analyze|survey|review literature)\b",
        r"\b(what is the latest|recent findings|current state of)\b",
        r"\b(papers?|articles?|publications?|journals?)\b",
        r"\b(according to|based on research)\b",
    ],
    "analysis": [
        r"\b(analyze|analysis|examine|evaluate|assess|compare)\b",
        r"\b(pros and cons|advantages|disadvantages|trade-?offs?)\b",
        r"\b(breakdown|break down|dissect)\b",
    ],
    "coding": [
        r"\b(code|programming?|implement|function|class|method)\b",
        r"\b(python|javascript|typescript|java|rust|go|c\+\+)\b",
        r"\b(bug|debug|fix|error|exception|refactor)\b",
        r"\b(api|endpoint|database|query|sql)\b",
        r"\b(git|commit|merge|branch)\b",
    ],
    "planning": [
        r"\b(plan|planning|strategy|roadmap|schedule)\b",
        r"\b(steps?|phases?|milestones?|timeline)\b",
        r"\b(how (should|can|do) (i|we)|what steps)\b",
        r"\b(project|initiative|goal|objective)\b",
    ],
    "creative": [
        r"\b(write|create|generate|compose|draft)\b",
        r"\b(story|poem|essay|article|blog|content)\b",
        r"\b(creative|imaginative|fiction|narrative)\b",
        r"\b(brainstorm|ideas?|suggestions?)\b",
    ],
    "explanation": [
        r"\b(explain|what is|what are|how does|how do)\b",
        r"\b(mean|means|meaning|definition|define)\b",
        r"\b(understand|clarify|elaborate)\b",
        r"\b(why (is|are|does|do)|reason)\b",
    ],
    "comparison": [
        r"\b(compare|comparison|versus|vs\.?|difference)\b",
        r"\b(better|worse|prefer|which (one|is))\b",
        r"\b(similarities|differences|contrast)\b",
    ],
    "recommendation": [
        r"\b(recommend|suggestion|advice|best|top)\b",
        r"\b(should (i|we)|what (should|would) you)\b",
        r"\b(choice|choose|pick|select|option)\b",
    ],
    "problem_solving": [
        r"\b(solve|solution|fix|resolve|troubleshoot)\b",
        r"\b(issue|problem|challenge|difficulty)\b",
        r"\b(how (to|can) (i|we)|help me)\b",
        r"\b(stuck|blocked|cannot|can't|won't)\b",
    ],
    "summarization": [
        r"\b(summarize|summary|summarise|tldr|tl;dr)\b",
        r"\b(brief|overview|gist|main points)\b",
        r"\b(in short|in brief|key takeaways)\b",
    ],
    # Trivial categories
    "reminder": [
        r"\b(remind|reminder|don'?t forget)\b",
        r"\b(at \d|in \d+ (minutes?|hours?|days?))\b",
        r"\b(tomorrow|tonight|next week)\b",
    ],
    "timer": [
        r"\b(set (a )?timer|start (a )?timer|countdown)\b",
        r"\b(\d+ (seconds?|minutes?|hours?))\b",
    ],
    "greeting": [
        r"^(hi|hello|hey|good (morning|afternoon|evening)|greetings)\b",
        r"^(what'?s up|howdy|yo)\b",
    ],
    "acknowledgment": [
        r"^(thanks?|thank you|ok|okay|got it|understood)\b",
        r"^(sure|alright|great|perfect|sounds good)\b",
    ],
    "simple_query": [
        r"^(what time|what'?s the (time|date|weather))\b",
        r"^(who (is|was)|when (is|was|did))\b",
        r"^(where (is|are))\b",
    ],
}

# Categories considered trivial (don't need reshaping or CoVe)
TRIVIAL_CATEGORIES = {"reminder", "timer", "greeting", "acknowledgment", "simple_query"}


class HeuristicClassifier(IntentClassifier):
    """
    Heuristic-based intent classifier using keyword matching.

    Uses regex patterns to classify prompts into categories.
    No ML dependencies required. Suitable for initial deployment
    before training a proper classifier.
    """

    def __init__(
        self,
        patterns: Optional[dict[str, list[str]]] = None,
        trivial_categories: Optional[set[str]] = None,
    ):
        """
        Initialize the heuristic classifier.

        Args:
            patterns: Custom category patterns (defaults to CATEGORY_PATTERNS).
            trivial_categories: Categories to mark as trivial (defaults to TRIVIAL_CATEGORIES).
        """
        self.patterns = patterns or CATEGORY_PATTERNS
        self.trivial_categories = trivial_categories or TRIVIAL_CATEGORIES
        # Pre-compile patterns for performance
        self._compiled: dict[str, list[re.Pattern]] = {
            category: [re.compile(p, re.IGNORECASE) for p in patterns]
            for category, patterns in self.patterns.items()
        }

    def classify(self, prompt: str) -> ClassificationResult:
        """
        Classify a prompt using keyword matching.

        Scores each category based on pattern matches and returns
        the highest-scoring category.

        Args:
            prompt: The raw user input.

        Returns:
            ClassificationResult with detected category.
        """
        if not prompt or not prompt.strip():
            return ClassificationResult.trivial("empty")

        prompt_lower = prompt.lower().strip()
        scores: dict[str, float] = {}

        # Score each category
        for category, patterns in self._compiled.items():
            score = 0.0
            for pattern in patterns:
                matches = pattern.findall(prompt_lower)
                score += len(matches) * 0.2  # 0.2 per match
            scores[category] = min(score, 1.0)  # Cap at 1.0

        # Find best category
        if not scores or all(s == 0 for s in scores.values()):
            # No matches - default to general
            return ClassificationResult(
                category="general",
                confidence=0.3,
                subcategories=[],
                is_trivial=False,
                raw_scores=scores,
            )

        sorted_categories = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_category, best_score = sorted_categories[0]

        # Get subcategories (others with score > 0.3)
        subcategories = [
            cat for cat, score in sorted_categories[1:4]
            if score >= 0.3
        ]

        # Check if trivial
        is_trivial = best_category in self.trivial_categories

        # Adjust confidence based on clarity
        if len(subcategories) == 0 and best_score >= 0.4:
            confidence = min(best_score + 0.2, 1.0)  # Clear signal
        elif len(subcategories) >= 2:
            confidence = max(best_score - 0.1, 0.3)  # Ambiguous
        else:
            confidence = best_score

        return ClassificationResult(
            category=best_category,
            confidence=confidence,
            subcategories=subcategories,
            is_trivial=is_trivial,
            raw_scores=scores,
        )

    def supported_categories(self) -> list[str]:
        """Return list of supported categories."""
        return list(self.patterns.keys())


# Default classifier instance
_default_classifier: Optional[IntentClassifier] = None


def get_classifier() -> IntentClassifier:
    """
    Get the default intent classifier.

    Returns a singleton HeuristicClassifier instance.
    Can be replaced with a custom classifier via set_classifier().

    Returns:
        The current intent classifier.
    """
    global _default_classifier
    if _default_classifier is None:
        _default_classifier = HeuristicClassifier()
    return _default_classifier


def set_classifier(classifier: IntentClassifier) -> None:
    """
    Set a custom intent classifier.

    Allows replacing the default heuristic classifier with
    an ML-based or custom implementation.

    Args:
        classifier: The classifier to use.
    """
    global _default_classifier
    _default_classifier = classifier


def classify_prompt(prompt: str) -> ClassificationResult:
    """
    Convenience function to classify a prompt.

    Uses the default classifier (heuristic or custom).

    Args:
        prompt: The raw user input.

    Returns:
        ClassificationResult with detected category.
    """
    return get_classifier().classify(prompt)
