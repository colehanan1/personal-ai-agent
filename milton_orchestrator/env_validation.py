"""Environment validation helpers for Milton bootstrap scripts."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional


REQUIRED_ENV_KEYS = ("PERPLEXITY_API_KEY", "TARGET_REPO")
OPTIONAL_ENV_KEYS = ("LLM_API_URL", "WEAVIATE_URL")
PLACEHOLDER_VALUES = {
    "your_perplexity_api_key_here",
    "YOUR_API_KEY_HERE",
    "YOUR_KEY_HERE",
}


@dataclass
class EnvValidationResult:
    """Structured result for environment validation."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: Path) -> dict[str, str]:
    """Load a .env file into a dict without mutating os.environ."""
    env: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        env[key] = _strip_quotes(value.strip())
    return env


def validate_env_values(
    env: Mapping[str, str], repo_root: Optional[Path] = None
) -> EnvValidationResult:
    """Validate required env vars and basic URL/path constraints."""
    result = EnvValidationResult()

    for key in REQUIRED_ENV_KEYS:
        value = env.get(key, "").strip()
        if not value or value in PLACEHOLDER_VALUES:
            result.errors.append(
                f"{key} is required. Set it in .env (see .env.example)."
            )

    target_repo = env.get("TARGET_REPO", "").strip()
    if target_repo:
        repo_path = Path(target_repo).expanduser()
        if not repo_path.exists():
            result.errors.append(f"TARGET_REPO does not exist: {repo_path}")
        elif not repo_path.is_dir():
            result.errors.append(f"TARGET_REPO is not a directory: {repo_path}")

    llm_url = env.get("LLM_API_URL", "").strip()
    if llm_url:
        if not llm_url.startswith("http"):
            result.errors.append("LLM_API_URL must start with http or https.")
    else:
        result.warnings.append(
            "LLM_API_URL not set; defaulting to http://localhost:8000."
        )

    weaviate_url = env.get("WEAVIATE_URL", "").strip()
    if weaviate_url:
        if not weaviate_url.startswith("http"):
            result.errors.append("WEAVIATE_URL must start with http or https.")
    else:
        if repo_root and (repo_root / "docker-compose.yml").exists():
            result.warnings.append(
                "WEAVIATE_URL not set; defaulting to http://localhost:8080."
            )
        else:
            result.warnings.append(
                "WEAVIATE_URL not set; memory store checks will be skipped."
            )

    return result


def validate_env_file(path: Path, repo_root: Optional[Path] = None) -> EnvValidationResult:
    """Load and validate a .env file."""
    env = load_env_file(path)
    return validate_env_values(env, repo_root=repo_root)


def _print_messages(result: EnvValidationResult) -> None:
    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    for warning in result.warnings:
        print(f"WARN: {warning}", file=sys.stderr)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Milton .env configuration.")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file (default: .env)",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root for relative checks (default: .)",
    )
    args = parser.parse_args(argv)

    env_path = Path(args.env_file).expanduser()
    if not env_path.exists():
        print(
            f"ERROR: .env file not found at {env_path}. "
            "Run: cp .env.example .env",
            file=sys.stderr,
        )
        return 1

    repo_root = Path(args.repo_root).expanduser()
    result = validate_env_file(env_path, repo_root=repo_root)
    _print_messages(result)

    if result.errors:
        return 1

    print("Environment validation OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
