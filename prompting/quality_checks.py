"""
Prompt quality validation for agent-facing prompts.

Ensures prompts include required elements:
- Explicit inputs/outputs
- Constraints
- Testing instructions

If quality checks fail, prompts can be revised with heuristic additions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class QualityCheckResult:
    """
    Result of prompt quality check.

    Attributes:
        passed: Whether all quality checks passed.
        issues: List of issues found (empty if passed).
        score: Quality score from 0.0 to 1.0.
    """

    passed: bool
    issues: list[str]
    score: float

    @property
    def needs_revision(self) -> bool:
        """Check if the prompt needs revision based on quality issues."""
        return not self.passed and len(self.issues) > 0


# Required elements for agent-facing prompts
REQUIRED_ELEMENTS: dict[str, dict] = {
    "inputs_outputs": {
        "patterns": [
            r"\b(input|output|return|parameter|argument|result)\b",
            r"\b(takes?|accepts?|produces?|generates?|yields?|expects?)\b",
            r"\b(receives?|provides?|sends?)\b",
        ],
        "description": "explicit inputs/outputs",
    },
    "constraints": {
        "patterns": [
            r"\b(constraint|requirement|must|should|shall|limit)\b",
            r"\b(boundary|restriction|rule|condition|ensure)\b",
            r"\b(avoid|don't|do not|never|always)\b",
        ],
        "description": "constraints",
    },
    "testing": {
        "patterns": [
            r"\b(test|testing|verify|validation|check|assert)\b",
            r"\b(edge case|corner case|error handling)\b",
            r"\b(coverage|unit test|integration test)\b",
        ],
        "description": "testing instructions",
    },
}


def check_prompt_quality(prompt: str) -> QualityCheckResult:
    """
    Check if a prompt meets quality requirements for agent-facing prompts.

    A quality prompt must include:
    - Explicit inputs/outputs (what the task expects and produces)
    - Constraints (rules and limitations)
    - Testing instructions (how to verify correctness)

    Args:
        prompt: The prompt to check.

    Returns:
        QualityCheckResult with pass/fail status, issues, and score.
    """
    issues: list[str] = []
    elements_found = 0

    for element_name, element_config in REQUIRED_ELEMENTS.items():
        patterns = element_config["patterns"]
        description = element_config["description"]

        found = any(re.search(p, prompt, re.IGNORECASE) for p in patterns)

        if found:
            elements_found += 1
        else:
            issues.append(f"Missing {description}")

    total_elements = len(REQUIRED_ELEMENTS)
    score = elements_found / total_elements if total_elements > 0 else 0.0
    passed = len(issues) == 0

    return QualityCheckResult(
        passed=passed,
        issues=issues,
        score=score,
    )


def revise_prompt_for_quality(
    prompt: str,
    issues: list[str],
) -> str:
    """
    Revise a prompt to address quality issues.

    Uses heuristic additions to add missing elements.
    Each missing element gets a section appended to the prompt.

    Args:
        prompt: Original prompt.
        issues: Quality issues to address.

    Returns:
        Revised prompt with missing elements added.
    """
    additions: list[str] = []

    if "Missing explicit inputs/outputs" in issues:
        additions.append(
            "\n\n## Expected Inputs/Outputs\n"
            "- Clearly define what inputs are expected\n"
            "- Specify the expected output format and content\n"
            "- Document any return values or side effects"
        )

    if "Missing constraints" in issues:
        additions.append(
            "\n\n## Constraints\n"
            "- Follow existing code conventions and patterns\n"
            "- Handle edge cases appropriately\n"
            "- Ensure backward compatibility where applicable\n"
            "- Avoid breaking changes to existing interfaces"
        )

    if "Missing testing instructions" in issues:
        additions.append(
            "\n\n## Testing Requirements\n"
            "- Write unit tests for new functionality\n"
            "- Verify edge cases are handled correctly\n"
            "- Run existing tests to ensure no regressions\n"
            "- Test error handling paths"
        )

    return prompt + "".join(additions)
