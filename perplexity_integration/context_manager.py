"""
Repository context loader for enriching Perplexity prompts

Extracts and caches repository metadata to provide context-aware prompts.
Context helps Perplexity synthesize better answers by understanding the
codebase structure and technologies used.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class RepositoryContext:
    """Container for repository metadata and context"""
    repo_path: Path
    primary_language: Optional[str] = None
    technologies: List[str] = None
    key_directories: List[str] = None
    description: Optional[str] = None
    context_summary: Optional[str] = None

    def __post_init__(self):
        if self.technologies is None:
            self.technologies = []
        if self.key_directories is None:
            self.key_directories = []


class RepositoryContextLoader:
    """
    Loads and caches repository context for prompt enrichment.

    Features:
    - Detects primary programming language
    - Identifies technologies and frameworks
    - Extracts key directory structure
    - Generates concise context summaries
    - Caches results for efficiency

    Example:
        loader = RepositoryContextLoader("/home/user/myproject")
        context = loader.load_context()
        summary = loader.get_context_summary()
        # Use summary in Perplexity prompts
    """

    # File patterns for technology detection
    TECH_INDICATORS = {
        "Python": [".py"],
        "JavaScript": [".js", ".jsx"],
        "TypeScript": [".ts", ".tsx"],
        "Go": [".go"],
        "Rust": [".rs"],
        "Java": [".java"],
    }

    FRAMEWORK_FILES = {
        "Flask": ["app.py", "wsgi.py", "requirements.txt"],
        "Django": ["manage.py", "settings.py"],
        "FastAPI": ["main.py", "requirements.txt"],
        "React": ["package.json", "src/App.jsx"],
        "Next.js": ["next.config.js", "pages"],
        "pytest": ["pytest.ini", "conftest.py", "tests"],
    }

    CONFIG_FILES = {
        "package.json": "Node.js project",
        "requirements.txt": "Python dependencies",
        "Pipfile": "Python (pipenv)",
        "pyproject.toml": "Python (modern)",
        "Cargo.toml": "Rust project",
        "go.mod": "Go module",
        "pom.xml": "Java (Maven)",
    }

    # Directories to ignore
    IGNORED_DIRS = {
        ".git", ".github", ".venv", "venv", "env",
        "node_modules", "__pycache__", ".pytest_cache",
        "build", "dist", "target", ".idea", ".vscode",
    }

    def __init__(self, repo_path: Path, cache_timeout: int = 300):
        """
        Initialize repository context loader.

        Args:
            repo_path: Path to repository root
            cache_timeout: Cache timeout in seconds (default 5 minutes)
        """
        self.repo_path = Path(repo_path).resolve()
        self.cache_timeout = cache_timeout
        self._cached_context: Optional[RepositoryContext] = None
        self._cache_timestamp: float = 0

        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
        if not self.repo_path.is_dir():
            raise ValueError(f"Repository path is not a directory: {repo_path}")

        logger.info(f"RepositoryContextLoader initialized for: {self.repo_path}")

    def load_context(self, force_refresh: bool = False) -> RepositoryContext:
        """
        Load repository context with caching.

        Args:
            force_refresh: Force refresh of cached context

        Returns:
            RepositoryContext with metadata
        """
        import time

        # Check cache
        if not force_refresh and self._cached_context:
            cache_age = time.time() - self._cache_timestamp
            if cache_age < self.cache_timeout:
                logger.debug(f"Using cached context (age: {cache_age:.1f}s)")
                return self._cached_context

        logger.info("Loading repository context...")

        # Detect primary language
        primary_language = self._detect_primary_language()

        # Detect technologies and frameworks
        technologies = self._detect_technologies()

        # Get key directories
        key_directories = self._get_key_directories()

        # Read description from README if available
        description = self._read_description()

        # Build context summary
        context_summary = self._build_context_summary(
            primary_language, technologies, key_directories
        )

        context = RepositoryContext(
            repo_path=self.repo_path,
            primary_language=primary_language,
            technologies=technologies,
            key_directories=key_directories,
            description=description,
            context_summary=context_summary,
        )

        # Cache the result
        self._cached_context = context
        self._cache_timestamp = time.time()

        logger.info(
            f"Context loaded: {primary_language}, "
            f"{len(technologies)} technologies, {len(key_directories)} dirs"
        )

        return context

    def _detect_primary_language(self) -> Optional[str]:
        """Detect primary programming language by file count"""
        language_counts: Dict[str, int] = {}

        try:
            for ext_pattern, lang in [(exts, lang) for lang, exts in self.TECH_INDICATORS.items() for exts in exts]:
                pattern = f"**/*{ext_pattern}"
                files = list(self.repo_path.glob(pattern))

                # Filter out ignored directories
                files = [
                    f for f in files
                    if not any(ignored in f.parts for ignored in self.IGNORED_DIRS)
                ]

                # Get the language for this extension
                for lang, exts in self.TECH_INDICATORS.items():
                    if ext_pattern in exts:
                        language_counts[lang] = language_counts.get(lang, 0) + len(files)
                        break

            if language_counts:
                primary = max(language_counts, key=language_counts.get)
                logger.debug(f"Detected primary language: {primary} ({language_counts[primary]} files)")
                return primary

        except Exception as e:
            logger.warning(f"Error detecting language: {e}")

        return None

    def _detect_technologies(self) -> List[str]:
        """Detect technologies and frameworks used"""
        technologies: Set[str] = set()

        try:
            # Check for framework indicators
            for framework, indicators in self.FRAMEWORK_FILES.items():
                for indicator in indicators:
                    indicator_path = self.repo_path / indicator
                    if indicator_path.exists():
                        technologies.add(framework)
                        break

            # Check for config files
            for config_file, tech in self.CONFIG_FILES.items():
                if (self.repo_path / config_file).exists():
                    technologies.add(tech)

            logger.debug(f"Detected technologies: {technologies}")

        except Exception as e:
            logger.warning(f"Error detecting technologies: {e}")

        return sorted(list(technologies))

    def _get_key_directories(self, max_depth: int = 2) -> List[str]:
        """Get key directory names (excluding ignored dirs)"""
        key_dirs: Set[str] = set()

        try:
            for item in self.repo_path.iterdir():
                if item.is_dir() and item.name not in self.IGNORED_DIRS:
                    key_dirs.add(item.name)

            logger.debug(f"Key directories: {key_dirs}")

        except Exception as e:
            logger.warning(f"Error getting directories: {e}")

        return sorted(list(key_dirs))

    def _read_description(self) -> Optional[str]:
        """Read project description from README"""
        readme_files = ["README.md", "README.rst", "README.txt", "README"]

        for readme in readme_files:
            readme_path = self.repo_path / readme
            if readme_path.exists():
                try:
                    content = readme_path.read_text(encoding="utf-8")
                    # Get first non-empty line (usually title)
                    for line in content.split("\n"):
                        line = line.strip()
                        if line and not line.startswith("#"):
                            # Return first 200 chars
                            return line[:200]
                        elif line.startswith("# "):
                            # Extract title from markdown header
                            return line[2:].strip()[:200]
                except Exception as e:
                    logger.warning(f"Error reading {readme}: {e}")

        return None

    def _build_context_summary(
        self,
        primary_language: Optional[str],
        technologies: List[str],
        key_directories: List[str],
    ) -> str:
        """
        Build concise context summary for prompt injection.

        Args:
            primary_language: Primary programming language
            technologies: List of detected technologies
            key_directories: Key directory names

        Returns:
            Concise context string optimized for token usage
        """
        parts = []

        if primary_language:
            parts.append(f"{primary_language} project")

        if technologies:
            tech_str = ", ".join(technologies[:3])  # Limit to top 3
            if len(technologies) > 3:
                tech_str += f" (+{len(technologies) - 3} more)"
            parts.append(f"using {tech_str}")

        if key_directories:
            dirs_str = ", ".join(key_directories[:4])  # Limit to top 4
            parts.append(f"with {dirs_str}")

        summary = " | ".join(parts) if parts else "Code repository"

        logger.debug(f"Context summary: {summary}")
        return summary

    def get_context_summary(self) -> str:
        """
        Get concise context summary (cached).

        Returns:
            Context summary string suitable for prompt injection
        """
        context = self.load_context()
        return context.context_summary or "Code repository"

    def get_prior_knowledge(self, topic: str) -> Optional[str]:
        """
        Retrieve prior knowledge about a topic from repository.

        Args:
            topic: Topic to search for (e.g., "authentication", "database")

        Returns:
            Relevant context if found, None otherwise

        Example:
            knowledge = loader.get_prior_knowledge("authentication")
            # Returns info about auth-related files/configs
        """
        logger.debug(f"Searching for prior knowledge: {topic}")

        # Search for relevant files
        topic_lower = topic.lower()
        relevant_files: List[Path] = []

        try:
            # Search in common doc locations
            doc_patterns = [
                f"**/*{topic_lower}*.*",
                f"**/docs/**/*.md",
                f"**/README*.md",
            ]

            for pattern in doc_patterns:
                files = self.repo_path.glob(pattern)
                for f in files:
                    if f.is_file() and not any(ignored in f.parts for ignored in self.IGNORED_DIRS):
                        relevant_files.append(f)

            if relevant_files:
                # Return summary of relevant files
                file_names = [f.name for f in relevant_files[:5]]
                return f"Related files found: {', '.join(file_names)}"

        except Exception as e:
            logger.warning(f"Error searching for prior knowledge: {e}")

        return None

    def to_dict(self) -> Dict[str, Any]:
        """Export context as dictionary"""
        context = self.load_context()
        return {
            "repo_path": str(context.repo_path),
            "primary_language": context.primary_language,
            "technologies": context.technologies,
            "key_directories": context.key_directories,
            "description": context.description,
            "context_summary": context.context_summary,
        }

    def to_json(self, filepath: Optional[Path] = None) -> str:
        """
        Export context as JSON.

        Args:
            filepath: Optional file path to save JSON

        Returns:
            JSON string
        """
        context_dict = self.to_dict()
        json_str = json.dumps(context_dict, indent=2)

        if filepath:
            Path(filepath).write_text(json_str)
            logger.info(f"Context saved to: {filepath}")

        return json_str
