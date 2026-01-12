"""
Self-upgrade capability for Milton.

Provides supervised, branch-based self-modification with strict guardrails.
"""

from .engine import run_self_upgrade, SelfUpgradeResult

__all__ = ["run_self_upgrade", "SelfUpgradeResult"]
