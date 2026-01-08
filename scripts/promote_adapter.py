#!/usr/bin/env python3
"""
LoRA Adapter Registry Management and Promotion

Manages adapter status transitions and provides registry operations.

Usage:
    python scripts/promote_adapter.py <run_id> --to-candidate
    python scripts/promote_adapter.py <run_id> --to-production
    python scripts/promote_adapter.py --rollback
    python scripts/promote_adapter.py --list
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)

REGISTRY_PATH = ROOT_DIR / "models" / "registry.json"


class AdapterRegistry:
    """Registry management class for LoRA adapters."""

    def __init__(self, registry_path: Path = REGISTRY_PATH):
        self.registry_path = registry_path
        self.registry = self.load(self.registry_path)

    @staticmethod
    def load(registry_path: Path = REGISTRY_PATH) -> Dict[str, Any]:
        """
        Load models/registry.json.

        Returns:
            Registry dictionary
        """
        if not registry_path.exists():
            raise FileNotFoundError(f"Registry not found at {registry_path}")

        with registry_path.open("r") as f:
            return json.load(f)

    def save(self):
        """Save registry to disk with atomic write."""
        # Write to temporary file first
        temp_path = self.registry_path.with_suffix(".json.tmp")
        with temp_path.open("w") as f:
            json.dump(self.registry, f, indent=2)

        # Atomic replace
        temp_path.replace(self.registry_path)
        logger.info(f"✓ Registry saved to {self.registry_path}")

    def get_adapter(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Get adapter entry by run_id.

        Args:
            run_id: Adapter run ID

        Returns:
            Adapter dict or None if not found
        """
        for adapter in self.registry["adapters"]:
            if adapter["run_id"] == run_id:
                return adapter
        return None

    def get_adapters_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Get all adapters with given status.

        Args:
            status: Status to filter by

        Returns:
            List of adapter dicts
        """
        return [a for a in self.registry["adapters"] if a["status"] == status]

    def get_production_adapter(self) -> Optional[Dict[str, Any]]:
        """
        Get current production adapter.

        Returns:
            Production adapter dict or None
        """
        production = self.get_adapters_by_status("production")
        return production[0] if production else None

    def promote_to_candidate(self, run_id: str):
        """
        Update adapter status to 'candidate'.

        Args:
            run_id: Adapter run ID
        """
        adapter = self.get_adapter(run_id)
        if not adapter:
            raise ValueError(f"Adapter {run_id} not found in registry")

        if adapter["status"] == "candidate":
            logger.info(f"Adapter {run_id} already candidate")
            return

        adapter["status"] = "candidate"
        adapter["promoted_at"] = datetime.now(timezone.utc).isoformat()

        logger.info(f"✓ Promoted {run_id} to candidate")
        self.save()

    def promote_to_production(self, run_id: str, force: bool = False):
        """
        Promote adapter to production.

        This will:
        1. Archive current production adapter
        2. Update new adapter to production status
        3. Save registry

        Args:
            run_id: Adapter run ID
            force: Skip confirmation prompt
        """
        adapter = self.get_adapter(run_id)
        if not adapter:
            raise ValueError(f"Adapter {run_id} not found in registry")

        if adapter["status"] == "production":
            logger.info(f"Adapter {run_id} already production")
            return

        # Get current production
        current_production = self.get_production_adapter()

        # Confirmation
        if not force:
            print(f"\n⚠️  Promotion to PRODUCTION")
            print(f"   New adapter: {run_id}")
            print(f"   Status: {adapter['status']} → production")

            if current_production:
                print(f"   Current production: {current_production['run_id']} (will be archived)")

            if "evaluation" in adapter:
                print(f"\n   Evaluation metrics:")
                eval_data = adapter["evaluation"]
                if "test_set" in eval_data:
                    for k, v in eval_data["test_set"].items():
                        print(f"     {k}: {v}")
                if "task_benchmarks" in eval_data:
                    pass_rate = eval_data["task_benchmarks"].get("overall_pass_rate", 0.0)
                    print(f"     Task pass rate: {pass_rate:.1%}")

            response = input("\n   Proceed? [y/N]: ")
            if response.lower() != 'y':
                print("   Cancelled")
                return

        # Archive current production
        if current_production:
            current_production["status"] = "archived"
            current_production["archived_at"] = datetime.now(timezone.utc).isoformat()
            logger.info(f"✓ Archived previous production: {current_production['run_id']}")

        # Promote to production
        adapter["status"] = "production"
        adapter["promoted_at"] = datetime.now(timezone.utc).isoformat()

        logger.info(f"✓ Promoted {run_id} to production")
        self.save()

    def archive_adapter(self, run_id: str):
        """
        Archive adapter.

        Args:
            run_id: Adapter run ID
        """
        adapter = self.get_adapter(run_id)
        if not adapter:
            raise ValueError(f"Adapter {run_id} not found in registry")

        adapter["status"] = "archived"
        adapter["archived_at"] = datetime.now(timezone.utc).isoformat()

        logger.info(f"✓ Archived {run_id}")
        self.save()

    def rollback_to_previous(self):
        """
        Restore previous production adapter.

        This finds the most recently archived adapter and promotes it
        back to production.
        """
        archived = self.get_adapters_by_status("archived")
        if not archived:
            raise ValueError("No archived adapters found for rollback")

        # Sort by archived_at (most recent first)
        archived.sort(key=lambda a: a.get("archived_at", ""), reverse=True)
        previous = archived[0]

        logger.info(f"Rolling back to {previous['run_id']}")
        self.promote_to_production(previous["run_id"], force=True)

    def list_adapters(self):
        """Print all adapters in registry."""
        if not self.registry["adapters"]:
            print("No adapters in registry")
            return

        print(f"\n{'Run ID':<25} {'Status':<12} {'Created':<12} {'Pass Rate':<10}")
        print("-" * 65)

        for adapter in self.registry["adapters"]:
            run_id = adapter["run_id"]
            status = adapter["status"]
            created = adapter.get("created_at", "")[:10]  # Just date

            # Get pass rate if available
            pass_rate = ""
            if "evaluation" in adapter and "task_benchmarks" in adapter["evaluation"]:
                pr = adapter["evaluation"]["task_benchmarks"].get("overall_pass_rate", 0.0)
                pass_rate = f"{pr:.1%}"

            # Add marker for production
            status_display = status
            if status == "production":
                status_display = f"{status} ★"

            print(f"{run_id:<25} {status_display:<12} {created:<12} {pass_rate:<10}")


def main():
    parser = argparse.ArgumentParser(description="Manage LoRA adapter registry")
    parser.add_argument("run_id", nargs="?", help="Adapter run ID")
    parser.add_argument("--to-candidate", action="store_true", help="Promote to candidate status")
    parser.add_argument("--to-production", action="store_true", help="Promote to production status")
    parser.add_argument("--archive", action="store_true", help="Archive adapter")
    parser.add_argument("--rollback", action="store_true", help="Rollback to previous production")
    parser.add_argument("--list", action="store_true", help="List all adapters")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompts")
    args = parser.parse_args()

    print("=== Milton Adapter Registry ===\n")

    try:
        registry = AdapterRegistry()

        if args.list:
            registry.list_adapters()

        elif args.rollback:
            registry.rollback_to_previous()
            print("\n✅ Rollback complete. Restart vLLM to apply changes.")

        elif args.run_id:
            if args.to_candidate:
                registry.promote_to_candidate(args.run_id)

            elif args.to_production:
                registry.promote_to_production(args.run_id, force=args.force)
                print("\n✅ Promotion complete. Restart vLLM to apply changes.")

            elif args.archive:
                registry.archive_adapter(args.run_id)

            else:
                # Show adapter info
                adapter = registry.get_adapter(args.run_id)
                if adapter:
                    print(json.dumps(adapter, indent=2))
                else:
                    print(f"Adapter {args.run_id} not found")
                    sys.exit(1)

        else:
            parser.print_help()

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
