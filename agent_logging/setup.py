"""
Logging Setup
Configures structured logging for all agents and modules.
"""
import logging
import logging.handlers
import os
import sys
from typing import Optional
from datetime import datetime

from milton_orchestrator.state_paths import resolve_state_dir


def setup_logging(
    agent_name: str,
    log_dir: Optional[str] = None,
    log_level: str = "INFO",
    console_output: bool = True,
) -> logging.Logger:
    """
    Setup structured logging for an agent.

    Creates rotating file handler and optional console handler.

    Args:
        agent_name: Name of the agent (CORTEX, NEXUS, FRONTIER, etc.)
        log_dir: Directory for log files (defaults to ~/.local/state/milton/logs/{agent_name}/)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        console_output: Whether to also log to console

    Returns:
        Configured logger instance

    Example:
        >>> from logging import setup_logging
        >>> logger = setup_logging("CORTEX")
        >>> logger.info("Task started")
        >>> logger.error("Task failed", exc_info=True)
    """
    # Determine log directory
    if log_dir is None:
        log_dir = resolve_state_dir() / "logs" / agent_name.lower()
    else:
        log_dir = os.path.expanduser(log_dir)

    # Create directory if needed
    os.makedirs(log_dir, exist_ok=True)

    # Get logger
    logger = logging.getLogger(agent_name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create formatters
    detailed_formatter = logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    simple_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # File handler - rotating by size
    log_file = os.path.join(
        log_dir, f"{agent_name.lower()}_{datetime.now().strftime('%Y%m%d')}.log"
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)

    # Console handler (optional)
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        console_handler.setFormatter(simple_formatter)
        logger.addHandler(console_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    logger.info(f"{agent_name} logging initialized")
    logger.debug(f"Log file: {log_file}")

    return logger


def setup_root_logging(log_level: str = "INFO") -> None:
    """
    Setup basic root logger configuration.

    Args:
        log_level: Logging level
    """
    log_dir = resolve_state_dir() / "logs"
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"system_{datetime.now().strftime('%Y%m%d')}.log")

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
            ),
            logging.StreamHandler(sys.stdout),
        ],
    )


def get_agent_logger(agent_name: str) -> logging.Logger:
    """
    Get or create logger for an agent.

    Args:
        agent_name: Name of the agent

    Returns:
        Logger instance
    """
    logger = logging.getLogger(agent_name)

    # If not configured yet, setup logging
    if not logger.handlers:
        setup_logging(agent_name)

    return logger


# Pre-configure loggers for main agents
def configure_agent_loggers() -> None:
    """Pre-configure loggers for all main agents."""
    agents = ["CORTEX", "NEXUS", "FRONTIER"]

    for agent in agents:
        setup_logging(agent, log_level=os.getenv("LOG_LEVEL", "INFO"))


if __name__ == "__main__":
    # Test logging setup
    logger = setup_logging("TEST_AGENT", console_output=True)

    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")

    try:
        1 / 0
    except ZeroDivisionError:
        logger.error("Caught exception", exc_info=True)

    print(f"\nLog file created in: {resolve_state_dir() / 'logs' / 'test_agent'}/")
