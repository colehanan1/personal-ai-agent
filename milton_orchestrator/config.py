"""Configuration management for Milton Orchestrator"""

import os
import shlex
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
    claude_topic: str
    codex_topic: str

    # Perplexity settings
    perplexity_api_key: str
    perplexity_model: str
    perplexity_timeout: int
    perplexity_max_retries: int

    # Claude Code settings
    claude_bin: str
    target_repo: Path

    # Codex CLI settings
    codex_bin: str
    codex_model: str
    codex_timeout: int
    codex_extra_args: list[str]
    enable_codex_fallback: bool
    codex_fallback_on_any_failure: bool
    claude_fallback_on_limit: bool

    # Routing and mode controls
    enable_prefix_routing: bool
    enable_claude_pipeline: bool
    enable_codex_pipeline: bool
    enable_research_mode: bool
    enable_reminders: bool
    perplexity_in_claude_mode: bool
    perplexity_in_codex_mode: bool
    perplexity_in_research_mode: bool

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

        def parse_bool(value: Optional[str], default: bool) -> bool:
            if value is None:
                return default
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
            return default

        def parse_fallback_mode(value: Optional[str]) -> tuple[bool, bool]:
            if value is None:
                return True, False
            normalized = value.strip().lower()
            if normalized in {"always", "any", "all"}:
                return True, True
            if normalized in {"1", "true", "yes", "on"}:
                return True, False
            if normalized in {"0", "false", "no", "off"}:
                return False, False
            return True, False

        def parse_extra_args(value: Optional[str]) -> list[str]:
            if not value:
                return []
            return shlex.split(value)

        # ntfy settings
        ntfy_base_url = os.getenv("NTFY_BASE_URL", "https://ntfy.sh")
        ask_topic = os.getenv("ASK_TOPIC", "milton-briefing-code-ask")
        answer_topic = os.getenv("ANSWER_TOPIC", "milton-briefing-code")
        claude_topic = os.getenv("CLAUDE_TOPIC", "").strip()
        codex_topic = os.getenv("CODEX_TOPIC", "").strip()

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

        # Processing settings
        request_timeout = int(os.getenv("REQUEST_TIMEOUT", "600"))
        ntfy_reconnect_backoff_max = int(os.getenv("NTFY_RECONNECT_BACKOFF_MAX", "300"))

        # Codex CLI settings
        codex_bin = os.getenv("CODEX_BIN", "codex")
        codex_model = os.getenv("CODEX_MODEL", "gpt-5.2-codex")
        codex_timeout = int(os.getenv("CODEX_TIMEOUT", str(request_timeout)))
        codex_extra_args = parse_extra_args(os.getenv("CODEX_EXTRA_ARGS", ""))
        enable_codex_fallback, codex_fallback_on_any_failure = parse_fallback_mode(
            os.getenv("ENABLE_CODEX_FALLBACK")
        )
        claude_fallback_on_limit = parse_bool(
            os.getenv("CLAUDE_FALLBACK_ON_LIMIT"), True
        )

        enable_prefix_routing = parse_bool(
            os.getenv("ENABLE_PREFIX_ROUTING"), True
        )
        enable_claude_pipeline = parse_bool(
            os.getenv("ENABLE_CLAUDE_PIPELINE"), True
        )
        enable_codex_pipeline = parse_bool(
            os.getenv("ENABLE_CODEX_PIPELINE"), True
        )
        enable_research_mode = parse_bool(
            os.getenv("ENABLE_RESEARCH_MODE"), True
        )
        enable_reminders = parse_bool(
            os.getenv("ENABLE_REMINDERS"), True
        )
        perplexity_in_claude_mode = parse_bool(
            os.getenv("PERPLEXITY_IN_CLAUDE_MODE"), True
        )
        perplexity_in_codex_mode = parse_bool(
            os.getenv("PERPLEXITY_IN_CODEX_MODE"), True
        )
        perplexity_in_research_mode = parse_bool(
            os.getenv("PERPLEXITY_IN_RESEARCH_MODE"), True
        )

        # Logging and state
        home = Path.home()
        log_dir = Path(os.getenv("LOG_DIR", home / ".local/state/milton_orchestrator/logs"))
        state_dir = Path(os.getenv("STATE_DIR", home / ".local/state/milton_orchestrator"))

        log_dir.mkdir(parents=True, exist_ok=True)
        state_dir.mkdir(parents=True, exist_ok=True)

        max_output_size = int(os.getenv("MAX_OUTPUT_SIZE", "4000"))

        return cls(
            ntfy_base_url=ntfy_base_url,
            ask_topic=ask_topic,
            answer_topic=answer_topic,
            claude_topic=claude_topic,
            codex_topic=codex_topic,
            perplexity_api_key=perplexity_api_key,
            perplexity_model=perplexity_model,
            perplexity_timeout=perplexity_timeout,
            perplexity_max_retries=perplexity_max_retries,
            claude_bin=claude_bin,
            target_repo=target_repo_path,
            codex_bin=codex_bin,
            codex_model=codex_model,
            codex_timeout=codex_timeout,
            codex_extra_args=codex_extra_args,
            enable_codex_fallback=enable_codex_fallback,
            codex_fallback_on_any_failure=codex_fallback_on_any_failure,
            claude_fallback_on_limit=claude_fallback_on_limit,
            enable_prefix_routing=enable_prefix_routing,
            enable_claude_pipeline=enable_claude_pipeline,
            enable_codex_pipeline=enable_codex_pipeline,
            enable_research_mode=enable_research_mode,
            enable_reminders=enable_reminders,
            perplexity_in_claude_mode=perplexity_in_claude_mode,
            perplexity_in_codex_mode=perplexity_in_codex_mode,
            perplexity_in_research_mode=perplexity_in_research_mode,
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
