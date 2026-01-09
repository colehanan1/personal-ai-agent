"""
Memory hook interface for the prompting middleware.

Provides integration with Milton's memory subsystem for storing:
- Reshaped prompts
- Verification artifacts
- Pipeline debug information

Degrades gracefully when the memory backend is unavailable.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .types import PipelineArtifacts, PromptSpec

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc)


class MemoryHookError(Exception):
    """Error during memory hook operation."""

    pass


class MemoryHook:
    """
    Interface for storing prompting pipeline artifacts to memory.

    Integrates with Milton's memory subsystem (Weaviate or JSONL).
    Fails gracefully when memory is unavailable.

    Attributes:
        repo_root: Path to the repository root (for locating memory backend).
        enabled: Whether memory storage is enabled.
    """

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        enabled: bool = True,
    ):
        """
        Initialize the memory hook.

        Args:
            repo_root: Path to repository root. Defaults to auto-detection.
            enabled: Whether to attempt memory storage.
        """
        self.repo_root = repo_root
        self.enabled = enabled
        self._backend: Optional[Any] = None
        self._backend_checked = False
        self._memory_available = False

    def _check_memory_availability(self) -> bool:
        """
        Check if the memory backend is available.

        Caches the result to avoid repeated checks.

        Returns:
            True if memory is available, False otherwise.
        """
        if self._backend_checked:
            return self._memory_available

        self._backend_checked = True

        try:
            from memory.backends import backend_status, get_backend

            status = backend_status(repo_root=self.repo_root)
            if status.mode in ("weaviate", "jsonl"):
                self._backend = get_backend(repo_root=self.repo_root)
                self._memory_available = True
                logger.debug(f"Memory backend available: {status.mode}")
            else:
                logger.warning(f"Memory backend not available: {status.detail}")
                self._memory_available = False
        except ImportError:
            logger.warning("Memory module not available - running without memory storage")
            self._memory_available = False
        except Exception as e:
            logger.warning(f"Failed to initialize memory backend: {e}")
            self._memory_available = False

        return self._memory_available

    def is_available(self) -> bool:
        """
        Check if memory storage is available.

        Returns:
            True if memory can be used, False otherwise.
        """
        if not self.enabled:
            return False
        return self._check_memory_availability()

    def store_reshaped_prompt(
        self,
        prompt_spec: "PromptSpec",
        agent_name: str = "prompting",
    ) -> Optional[str]:
        """
        Store a reshaped prompt to memory.

        Creates a memory item with the original and reshaped prompts,
        along with transformation metadata.

        Args:
            prompt_spec: The prompt specification to store.
            agent_name: Agent name for the memory item.

        Returns:
            Memory item ID if stored, None if storage failed.
        """
        if not self.is_available():
            logger.debug("Memory not available - skipping reshaped prompt storage")
            return None

        try:
            from memory.schema import MemoryItem
            from memory.store import add_memory

            content = json.dumps({
                "type": "reshaped_prompt",
                "original": prompt_spec.original_prompt,
                "reshaped": prompt_spec.reshaped_prompt,
                "category": prompt_spec.category,
                "transformations": prompt_spec.transformations_applied,
                "was_modified": prompt_spec.was_modified(),
            })

            item = MemoryItem(
                agent=agent_name,
                type="crumb",
                content=content,
                tags=["prompting", "reshaped_prompt", prompt_spec.category],
                importance=0.3,  # Low importance - debug artifact
                source="prompting_pipeline",
                request_id=prompt_spec.request_id,
            )

            memory_id = add_memory(item, repo_root=self.repo_root, backend=self._backend)
            logger.debug(f"Stored reshaped prompt: {memory_id}")
            return memory_id

        except Exception as e:
            logger.warning(f"Failed to store reshaped prompt: {e}")
            return None

    def store_verification_artifacts(
        self,
        artifacts: "PipelineArtifacts",
        agent_name: str = "prompting",
    ) -> Optional[str]:
        """
        Store verification artifacts to memory.

        Creates a memory item with the CoVe questions, findings,
        and verification results.

        Args:
            artifacts: The pipeline artifacts to store.
            agent_name: Agent name for the memory item.

        Returns:
            Memory item ID if stored, None if storage failed.
        """
        if not self.is_available():
            logger.debug("Memory not available - skipping artifact storage")
            return None

        if not artifacts.has_verification():
            logger.debug("No verification artifacts to store")
            return None

        try:
            from memory.schema import MemoryItem
            from memory.store import add_memory

            content = json.dumps({
                "type": "verification_artifacts",
                "request_id": artifacts.request_id,
                "draft_response": artifacts.draft_response[:500] if artifacts.draft_response else None,
                "questions_count": len(artifacts.cove_questions),
                "findings_count": len(artifacts.cove_findings),
                "verification_passed": artifacts.verification_passed(),
                "questions": [
                    {
                        "id": q.question_id,
                        "text": q.question_text,
                        "claim": q.target_claim,
                        "verified": q.verified,
                        "confidence": q.confidence,
                    }
                    for q in artifacts.cove_questions
                ],
                "findings": [
                    {
                        "id": f.finding_id,
                        "description": f.description,
                        "severity": f.severity.value,
                        "status": f.status.value,
                    }
                    for f in artifacts.cove_findings
                ],
            })

            # Determine importance based on findings
            importance = 0.3  # Default low
            if any(f.is_critical() for f in artifacts.cove_findings):
                importance = 0.7  # Higher if critical findings

            item = MemoryItem(
                agent=agent_name,
                type="crumb",
                content=content,
                tags=["prompting", "verification", "cove"],
                importance=importance,
                source="prompting_pipeline",
                request_id=artifacts.request_id,
            )

            memory_id = add_memory(item, repo_root=self.repo_root, backend=self._backend)
            logger.debug(f"Stored verification artifacts: {memory_id}")
            return memory_id

        except Exception as e:
            logger.warning(f"Failed to store verification artifacts: {e}")
            return None

    def store_pipeline_result(
        self,
        artifacts: "PipelineArtifacts",
        agent_name: str = "prompting",
    ) -> list[str]:
        """
        Store all relevant artifacts from a pipeline run.

        Stores both the reshaped prompt and verification artifacts
        if they exist.

        Args:
            artifacts: The pipeline artifacts to store.
            agent_name: Agent name for memory items.

        Returns:
            List of memory item IDs that were stored.
        """
        stored_ids: list[str] = []

        # Store reshaped prompt if modified
        if artifacts.prompt_spec and artifacts.prompt_spec.was_modified():
            prompt_id = self.store_reshaped_prompt(
                artifacts.prompt_spec,
                agent_name=agent_name,
            )
            if prompt_id:
                stored_ids.append(prompt_id)

        # Store verification artifacts
        if artifacts.has_verification():
            artifact_id = self.store_verification_artifacts(
                artifacts,
                agent_name=agent_name,
            )
            if artifact_id:
                stored_ids.append(artifact_id)

        return stored_ids


# Global memory hook instance
_memory_hook: Optional[MemoryHook] = None


def get_memory_hook(repo_root: Optional[Path] = None) -> MemoryHook:
    """
    Get the global memory hook instance.

    Creates a new hook if one doesn't exist.

    Args:
        repo_root: Optional repository root path.

    Returns:
        The memory hook instance.
    """
    global _memory_hook
    if _memory_hook is None:
        _memory_hook = MemoryHook(repo_root=repo_root)
    return _memory_hook


def reset_memory_hook() -> None:
    """Reset the global memory hook (mainly for testing)."""
    global _memory_hook
    _memory_hook = None
