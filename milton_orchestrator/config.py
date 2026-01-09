"""Configuration management for Milton Orchestrator"""

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .state_paths import resolve_state_dir

if TYPE_CHECKING:
    from prompting import PromptingConfig


@dataclass
class Config:
    """Configuration for the orchestrator"""

    # ntfy settings
    ntfy_base_url: str
    ntfy_max_chars: int
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
    claude_timeout: int
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

    # Output publishing
    output_dir: Path
    output_base_url: Optional[str]
    output_share_url: Optional[str]
    output_share_host: Optional[str]
    output_share_name: Optional[str]
    ntfy_max_inline_chars: int
    always_file_attachments: bool
    output_filename_template: str

    # Processing settings
    request_timeout: int
    ntfy_reconnect_backoff_max: int

    # Prompting middleware (optional - lazy loaded)
    prompting: Optional["PromptingConfig"] = field(default=None)

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

        def parse_timeout(value: Optional[str], default: int) -> int:
            if value is None:
                return default
            normalized = value.strip().lower()
            if normalized in {"none", "no", "off"}:
                return 0
            return int(normalized)

        # ntfy settings
        ntfy_base_url = os.getenv("NTFY_BASE_URL", "https://ntfy.sh")
        ask_topic = os.getenv("ASK_TOPIC", "milton-briefing-code-ask")
        answer_topic = os.getenv("ANSWER_TOPIC", "milton-briefing-code")
        claude_topic = os.getenv("CLAUDE_TOPIC", "").strip()
        codex_topic = os.getenv("CODEX_TOPIC", "").strip()
        ntfy_max_chars = int(os.getenv("NTFY_MAX_CHARS", "160"))

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
        claude_timeout = parse_timeout(os.getenv("CLAUDE_TIMEOUT"), 0)
        ntfy_reconnect_backoff_max = int(os.getenv("NTFY_RECONNECT_BACKOFF_MAX", "300"))

        # Codex CLI settings
        codex_bin = os.getenv("CODEX_BIN", "codex")
        codex_model = os.getenv("CODEX_MODEL", "gpt-5.2-codex")
        codex_timeout = parse_timeout(os.getenv("CODEX_TIMEOUT"), 0)
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
        state_dir = resolve_state_dir()
        log_dir = Path(os.getenv("LOG_DIR", state_dir / "logs"))

        output_dir = Path(
            os.getenv("OUTPUT_DIR", state_dir / "outputs")
        )
        output_base_url = os.getenv("OUTPUT_BASE_URL", "").strip() or None
        output_share_url = os.getenv("OUTPUT_SHARE_URL", "").strip() or None
        output_share_host = os.getenv("OUTPUT_SHARE_HOST", "").strip() or None
        output_share_name = os.getenv("OUTPUT_SHARE_NAME", "").strip() or None
        ntfy_max_inline_chars = int(os.getenv("NTFY_MAX_INLINE_CHARS", "3000"))
        always_file_attachments = parse_bool(
            os.getenv("ALWAYS_FILE_ATTACHMENTS"), False
        )
        output_filename_template = os.getenv(
            "OUTPUT_FILENAME_TEMPLATE", "milton_{request_id}.txt"
        )

        log_dir.mkdir(parents=True, exist_ok=True)
        state_dir.mkdir(parents=True, exist_ok=True)

        max_output_size = int(os.getenv("MAX_OUTPUT_SIZE", "4000"))

        output_dir.mkdir(parents=True, exist_ok=True)

        # Load prompting middleware config (optional)
        prompting_config = None
        try:
            from prompting import PromptingConfig
            prompting_config = PromptingConfig.from_env()
        except ImportError:
            pass  # Prompting module not available

        return cls(
            ntfy_base_url=ntfy_base_url,
            ntfy_max_chars=ntfy_max_chars,
            ask_topic=ask_topic,
            answer_topic=answer_topic,
            claude_topic=claude_topic,
            codex_topic=codex_topic,
            perplexity_api_key=perplexity_api_key,
            perplexity_model=perplexity_model,
            perplexity_timeout=perplexity_timeout,
            perplexity_max_retries=perplexity_max_retries,
            claude_bin=claude_bin,
            claude_timeout=claude_timeout,
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
            output_dir=output_dir,
            output_base_url=output_base_url,
            output_share_url=output_share_url,
            output_share_host=output_share_host,
            output_share_name=output_share_name,
            ntfy_max_inline_chars=ntfy_max_inline_chars,
            always_file_attachments=always_file_attachments,
            output_filename_template=output_filename_template,
            request_timeout=request_timeout,
            ntfy_reconnect_backoff_max=ntfy_reconnect_backoff_max,
            prompting=prompting_config,
        )

    def validate(self) -> None:
        """Validate configuration"""
        if not self.ntfy_base_url.startswith("http"):
            raise ValueError(f"Invalid NTFY_BASE_URL: {self.ntfy_base_url}")

        if not self.ask_topic or not self.answer_topic:
            raise ValueError("Both ASK_TOPIC and ANSWER_TOPIC must be set")

        if self.ntfy_max_chars <= 0:
            raise ValueError("NTFY_MAX_CHARS must be > 0")

        if self.ntfy_max_inline_chars <= 0:
            raise ValueError("NTFY_MAX_INLINE_CHARS must be > 0")

        if self.output_base_url and not self.output_base_url.startswith("http"):
            raise ValueError(f"Invalid OUTPUT_BASE_URL: {self.output_base_url}")

        if bool(self.output_share_host) ^ bool(self.output_share_name):
            raise ValueError(
                "OUTPUT_SHARE_HOST and OUTPUT_SHARE_NAME must be set together"
            )

        if not self.output_filename_template.strip():
            raise ValueError("OUTPUT_FILENAME_TEMPLATE must be non-empty")

        if self.claude_timeout < 0:
            raise ValueError("CLAUDE_TIMEOUT must be >= 0 (0 means no timeout)")

        if self.codex_timeout < 0:
            raise ValueError("CODEX_TIMEOUT must be >= 0 (0 means no timeout)")
