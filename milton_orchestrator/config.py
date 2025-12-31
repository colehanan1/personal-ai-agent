"""Configuration management for Milton Orchestrator"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """Configuration for the orchestrator"""

    # ntfy settings
    ntfy_base_url: str
    ask_topic: str
    answer_topic: str

    # Perplexity settings
    perplexity_api_key: str
    perplexity_model: str
    perplexity_timeout: int
    perplexity_max_retries: int

    # Claude Code settings
    claude_bin: str
    target_repo: Path

    # Logging and state
    log_dir: Path
    state_dir: Path
    max_output_size: int

    # Processing settings
    request_timeout: int
    ntfy_reconnect_backoff_max: int

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""

        # ntfy settings
        ntfy_base_url = os.getenv("NTFY_BASE_URL", "https://ntfy.sh")
        ask_topic = os.getenv("ASK_TOPIC", "milton-briefing-code-ask")
        answer_topic = os.getenv("ANSWER_TOPIC", "milton-briefing-code")

        # Perplexity settings
        perplexity_api_key = os.getenv("PERPLEXITY_API_KEY", "")
        if not perplexity_api_key:
            raise ValueError("PERPLEXITY_API_KEY environment variable is required")

        perplexity_model = os.getenv("PERPLEXITY_MODEL", "sonar-pro")
        perplexity_timeout = int(os.getenv("PERPLEXITY_TIMEOUT", "60"))
        perplexity_max_retries = int(os.getenv("PERPLEXITY_MAX_RETRIES", "3"))

        # Claude Code settings
        claude_bin = os.getenv("CLAUDE_BIN", "claude")
        target_repo = os.getenv("TARGET_REPO", "")
        if not target_repo:
            raise ValueError("TARGET_REPO environment variable is required")

        target_repo_path = Path(target_repo).expanduser().resolve()
        if not target_repo_path.exists():
            raise ValueError(f"TARGET_REPO does not exist: {target_repo_path}")
        if not target_repo_path.is_dir():
            raise ValueError(f"TARGET_REPO is not a directory: {target_repo_path}")

        # Logging and state
        home = Path.home()
        log_dir = Path(os.getenv("LOG_DIR", home / ".local/state/milton_orchestrator/logs"))
        state_dir = Path(os.getenv("STATE_DIR", home / ".local/state/milton_orchestrator"))

        log_dir.mkdir(parents=True, exist_ok=True)
        state_dir.mkdir(parents=True, exist_ok=True)

        max_output_size = int(os.getenv("MAX_OUTPUT_SIZE", "4000"))

        # Processing settings
        request_timeout = int(os.getenv("REQUEST_TIMEOUT", "600"))
        ntfy_reconnect_backoff_max = int(os.getenv("NTFY_RECONNECT_BACKOFF_MAX", "300"))

        return cls(
            ntfy_base_url=ntfy_base_url,
            ask_topic=ask_topic,
            answer_topic=answer_topic,
            perplexity_api_key=perplexity_api_key,
            perplexity_model=perplexity_model,
            perplexity_timeout=perplexity_timeout,
            perplexity_max_retries=perplexity_max_retries,
            claude_bin=claude_bin,
            target_repo=target_repo_path,
            log_dir=log_dir,
            state_dir=state_dir,
            max_output_size=max_output_size,
            request_timeout=request_timeout,
            ntfy_reconnect_backoff_max=ntfy_reconnect_backoff_max,
        )

    def validate(self) -> None:
        """Validate configuration"""
        if not self.ntfy_base_url.startswith("http"):
            raise ValueError(f"Invalid NTFY_BASE_URL: {self.ntfy_base_url}")

        if not self.ask_topic or not self.answer_topic:
            raise ValueError("Both ASK_TOPIC and ANSWER_TOPIC must be set")
