"""
NEXUS - Orchestration Hub
Coordinates between agents, generates briefings, and routes requests.
"""
import requests
from dataclasses import dataclass, field
from datetime import datetime
import logging
import os
import re
from typing import Any, Dict, Optional, List

from dotenv import load_dotenv

from integrations import (
    HomeAssistantAPI,
    WeatherAPI,
    ArxivAPI,
    NewsAPI,
    CalendarAPI,
    WebSearchAPI,
)
from agents.memory_hooks import (
    MemoryContextHook,
    memory_enabled,
    record_memory,
    should_store_responses,
)
from agents.tool_registry import (
    ToolDefinition,
    ToolResult,
    get_tool_registry,
)
from agents.contracts import (
    TaskRequest,
    TaskPriority,
    generate_task_id,
    generate_iso_timestamp,
)
from memory.retrieve import query_relevant, query_relevant_hybrid
from memory.status import record_retrieval
from memory.schema import MemoryItem
from milton_orchestrator.state_paths import resolve_state_dir
from phd_context import (
    get_phd_context,
    should_include_phd_context,
    get_phd_summary_for_agent,
    is_phd_related,
)

# Import prompting pipeline (optional - degrades gracefully if not available)
try:
    from prompting import PromptingPipeline, PromptingConfig, PipelineResult
    PROMPTING_AVAILABLE = True
except ImportError:
    PROMPTING_AVAILABLE = False
    PromptingPipeline = None
    PromptingConfig = None
    PipelineResult = None

load_dotenv()

logger = logging.getLogger(__name__)

# One-way phone mode prompt injection
# Used when requests come from ntfy/phone where user cannot respond to follow-ups
ONE_WAY_PHONE_MODE_PROMPT = """
## ONE-WAY CHANNEL MODE (ACTIVE)

This request came via a one-way channel (phone/ntfy). The user CANNOT respond to follow-up questions.

CRITICAL RULES:
1. NEVER ask clarifying questions - proceed with best-effort assumptions
2. NEVER ask "Can you provide more details?" or similar
3. NEVER include phrases like "I need more information" or "Please clarify"
4. If information is missing, state your assumption and proceed
5. Provide actionable output even if incomplete

REQUIRED RESPONSE FORMAT:
**Summary:** [1-2 sentence answer or action taken]

**Assumptions:** (if any missing info was assumed)
- [assumption 1]
- [assumption 2]

**Next Steps:**
- [actionable step 1]
- [actionable step 2]

END
"""

# Patterns that indicate clarification loop behavior (to be caught by post-guard)
CLARIFICATION_PATTERNS = [
    r"(?:can you|could you|please)\s+(?:provide|give|tell|share|clarify)",
    r"(?:need|require)\s+(?:more|additional|further)\s+(?:info|information|details|context)",
    r"(?:what|which)\s+(?:specifically|exactly)\s+(?:do you|would you)",
    r"(?:before I|to help you better|to assist you)",
    r"(?:unclear|ambiguous|vague)\s+(?:about|what)",
    r"I(?:'m| am) (?:not sure|uncertain|unsure) (?:about |what )",
    r"(?:please specify|specify which|which one)",
]


def detect_clarification_loop(response: str) -> bool:
    """
    Detect if a response contains clarification-seeking patterns.

    Returns True if the response appears to be asking for more info.
    """
    lowered = response.lower()

    # Count question marks (>2 suggests multiple clarifying questions)
    question_count = response.count("?")
    if question_count > 2:
        logger.debug(f"Clarification loop detected: {question_count} question marks")
        return True

    # Check for clarification patterns
    for pattern in CLARIFICATION_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            logger.debug(f"Clarification loop detected: matched pattern '{pattern}'")
            return True

    return False


def rewrite_to_one_way_format(response: str, original_query: str) -> str:
    """
    Rewrite a clarification-seeking response into one-way format.

    Extracts any useful content and reformats with assumptions and next steps.
    """
    # Extract any sentences that don't contain questions
    lines = response.split('\n')
    useful_lines = []
    questions = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if '?' in stripped:
            questions.append(stripped)
        else:
            useful_lines.append(stripped)

    # Build summary from non-question content
    summary = ' '.join(useful_lines[:2]) if useful_lines else "Proceeding with available information."
    if len(summary) > 200:
        summary = summary[:197] + "..."

    # Convert questions to assumptions
    assumptions = []
    for q in questions[:3]:  # Max 3 assumptions
        # Convert question to assumption
        assumption = q.rstrip('?').strip()
        assumption = re.sub(r'^(what|which|how|where|when|why|can you|could you|please)\s+', '', assumption, flags=re.I)
        assumption = re.sub(r'^(is|are|do|does|will|would)\s+', '', assumption, flags=re.I)
        if assumption and len(assumption) > 10:
            assumptions.append(f"Assuming: {assumption[:100]}")

    if not assumptions:
        assumptions = ["Proceeding with general context from request"]

    # Build next steps from query context
    next_steps = [
        "Review this response and provide additional context if needed",
        "Send a follow-up message with specific requirements",
    ]

    # Format the rewritten response
    result = f"""**Summary:** {summary}

**Assumptions:**
{chr(10).join(f'- {a}' for a in assumptions)}

**Next Steps:**
{chr(10).join(f'- {s}' for s in next_steps)}

END"""

    logger.info("Rewrote clarification-seeking response to one-way format")
    return result


@dataclass(frozen=True)
class RoutingDecision:
    route: str
    rationale: str
    context_ids: list[str] = field(default_factory=list)
    tool_name: Optional[str] = None


@dataclass(frozen=True)
class ContextBullet:
    text: str
    evidence_ids: list[str]


@dataclass(frozen=True)
class ContextPacket:
    query: str
    bullets: list[ContextBullet] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    kg_context: Optional[str] = None  # KG context section

    @property
    def context_ids(self) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for bullet in self.bullets:
            for evidence_id in bullet.evidence_ids:
                if evidence_id and evidence_id not in seen:
                    seen.add(evidence_id)
                    ordered.append(evidence_id)
        return ordered

    def to_prompt(self) -> str:
        lines = ["===MEMORY INJECTED==="]
        lines.append("CONTEXT PACKET (evidence-backed memory only)")
        if self.bullets:
            lines.append("Relevant memory bullets:")
            for bullet in self.bullets:
                evidence = ", ".join(bullet.evidence_ids)
                lines.append(f"- {bullet.text} [evidence: {evidence}]")
        else:
            lines.append("Relevant memory bullets: none")

        lines.append("Unknowns / assumptions:")
        if self.unknowns:
            for item in self.unknowns:
                lines.append(f"- Unknown: {item}")
        if self.assumptions:
            for item in self.assumptions:
                lines.append(f"- Assumption: {item}")
        if not self.unknowns and not self.assumptions:
            lines.append("- None")

        # Add KG context if available
        if self.kg_context:
            lines.append("")  # Blank line separator
            lines.append(self.kg_context)

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "bullets": [
                {"text": bullet.text, "evidence_ids": bullet.evidence_ids}
                for bullet in self.bullets
            ],
            "unknowns": list(self.unknowns),
            "assumptions": list(self.assumptions),
            "context_ids": self.context_ids,
        }


@dataclass(frozen=True)
class Response:
    text: str
    citations: list[str]
    route_used: str
    context_used: list[str]
    verified_badge: Optional[str] = None
    reshaped_from: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "citations": list(self.citations),
            "route_used": self.route_used,
            "context_used": list(self.context_used),
            "verified_badge": self.verified_badge,
            "reshaped_from": self.reshaped_from,
        }


class NEXUS:
    """
    NEXUS orchestration agent.

    Responsibilities:
    - Route user requests to appropriate agents
    - Generate morning and evening briefings
    - Coordinate between CORTEX and FRONTIER
    - Maintain conversational context
    - Handle bedtime routine
    """

    def __init__(
        self,
        model_url: Optional[str] = None,
        model_name: Optional[str] = None,
        adapter_name: Optional[str] = None,
    ):
        """
        Initialize NEXUS agent.

        Args:
            model_url: vLLM API URL (defaults to env var)
            model_name: Model name (defaults to env var)
            adapter_name: LoRA adapter name to load (optional)
        """
        self.model_url = (
            model_url
            or os.getenv("LLM_API_URL")
            or os.getenv("OLLAMA_API_URL", "http://localhost:8000")
        ).rstrip("/")
        self.model_name = (
            model_name
            or os.getenv("LLM_MODEL")
            or os.getenv("OLLAMA_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
        )
        self.system_prompt = self._load_system_prompt()

        # Initialize integrations
        self.home_assistant = HomeAssistantAPI()
        self.weather = WeatherAPI()
        self.arxiv = ArxivAPI()  # Note: Milton uses ArxivAPI not ArXivAPI
        self.news = NewsAPI()
        self.calendar = CalendarAPI()
        self.web_search = WebSearchAPI()

        self.web_lookup_enabled = str(os.getenv("WEB_LOOKUP", "")).lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self.web_lookup_max_results = int(os.getenv("WEB_LOOKUP_MAX_RESULTS", "5"))
        self.tool_registry = get_tool_registry()
        self._register_default_tools()
        
        # Initialize memory context hook with semantic search
        self.memory_hook = MemoryContextHook(
            agent="NEXUS",
            use_semantic=True,
            semantic_weight=0.5,  # Balanced hybrid for orchestration
            recency_bias=0.7,  # Higher recency bias for briefings
        )
        
        # Load LoRA adapter if specified
        self.adapter_info = None
        if adapter_name:
            self._load_adapter(adapter_name)
        elif os.getenv("NEXUS_ADAPTER"):
            self._load_adapter(os.getenv("NEXUS_ADAPTER"))

        # Initialize prompting pipeline if available
        self._prompting_pipeline: Optional["PromptingPipeline"] = None
        self._prompting_config: Optional["PromptingConfig"] = None
        if PROMPTING_AVAILABLE:
            try:
                config = PromptingConfig.from_env()
                self._prompting_config = config
                self._prompting_pipeline = PromptingPipeline(config=config)
                logger.info("Prompting pipeline initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize prompting pipeline: {e}")

        logger.info("NEXUS agent initialized with semantic memory context")

    def _load_adapter(self, adapter_name: str) -> None:
        """
        Load LoRA adapter information.
        
        Note: Actual adapter loading would happen at the LLM server level.
        This method loads adapter metadata for provenance tracking.
        
        Args:
            adapter_name: Name of adapter to load
        """
        try:
            from training.adapter_manager import AdapterManager
            
            manager = AdapterManager()
            adapter = manager.get_adapter(adapter_name)
            
            if adapter:
                self.adapter_info = adapter
                logger.info(
                    f"Loaded adapter metadata: {adapter_name} "
                    f"(quality={adapter.quality_score:.2%})"
                )
            else:
                logger.warning(f"Adapter not found: {adapter_name}")
                
        except Exception as e:
            logger.warning(f"Failed to load adapter metadata: {e}")

    def _load_system_prompt(self) -> str:
        """Load NEXUS system prompt from Prompts folder with PhD context."""
        from agents import load_agent_context
        base_prompt = load_agent_context("NEXUS")

        # Add PhD context to system prompt
        phd_summary = get_phd_summary_for_agent()
        enhanced_prompt = f"{base_prompt}\n\n{phd_summary}"

        return enhanced_prompt

    def _call_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2000,
        context_packet: Optional[ContextPacket] = None,
    ) -> str:
        """Call vLLM API for inference."""
        url = f"{self.model_url}/v1/chat/completions"
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("VLLM_API_KEY")
            or os.getenv("OLLAMA_API_KEY")
        )
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if context_packet:
            messages.append({"role": "system", "content": context_packet.to_prompt()})

        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }

        response = requests.post(url, json=payload, timeout=120, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _register_default_tools(self) -> None:
        self.register_tool(
            ToolDefinition(
                name="weather",
                description="Current weather lookup",
                keywords=("weather", "temperature", "forecast"),
                handler=self._tool_weather,
            ),
            replace=True,
        )
        self.register_tool(
            ToolDefinition(
                name="arxiv",
                description="arXiv paper search",
                keywords=("arxiv", "paper", "papers", "publication", "preprint"),
                handler=self._tool_arxiv,
            ),
            replace=True,
        )
        self.register_tool(
            ToolDefinition(
                name="reminder",
                description="Create, list, or cancel reminders",
                keywords=("remind", "reminder", "alarm", "alert", "notification", "schedule"),
                handler=self._tool_reminder,
            ),
            replace=True,
        )

    def register_tool(self, tool: ToolDefinition, replace: bool = True) -> None:
        self.tool_registry.register(tool, replace=replace)

    def _tool_weather(self, user_text: str) -> ToolResult:
        weather = self.weather.current_weather()
        summary = (
            f"{weather['location']}: {weather['temp']}°F, "
            f"{weather['condition']} (high {weather['high']}°F, low {weather['low']}°F)"
        )
        return ToolResult(text=summary, citations=["weather:openweathermap"])

    def _tool_arxiv(self, user_text: str) -> ToolResult:
        max_results = self._parse_max_results(user_text, default=3)
        papers = self.arxiv.search_papers(user_text, max_results=max_results)
        if not papers:
            return ToolResult(text="No papers found.", citations=[])

        lines = []
        citations: list[str] = []
        for paper in papers[:max_results]:
            title = paper.get("title", "Untitled")
            authors = ", ".join(paper.get("authors", [])[:3])
            arxiv_id = paper.get("arxiv_id", "unknown")
            pdf_url = paper.get("pdf_url")
            if pdf_url:
                citations.append(pdf_url)
            lines.append(f"- {title} ({authors}) [arXiv:{arxiv_id}]")

        return ToolResult(text="\n".join(lines), citations=citations)

    def _tool_reminder(self, user_text: str) -> ToolResult:
        """Handle reminder creation from natural language."""
        try:
            # Import here to avoid circular dependency
            import re

            # Dynamic imports to handle optional dependencies
            try:
                from milton_orchestrator.reminders import (
                    ReminderStore,
                    parse_time_expression,
                    format_timestamp_local,
                )
            except ImportError:
                return ToolResult(
                    text="Reminders system not available. Install with: pip install dateparser pytz",
                    citations=[],
                )

            # Get canonical database path
            from milton_orchestrator.state_paths import resolve_reminders_db_path
            db_path = resolve_reminders_db_path()

            # Check for list command
            if re.search(r'\b(list|show|view)\b.*\breminder', user_text, re.IGNORECASE):
                store = ReminderStore(db_path)
                reminders = store.list_reminders()
                store.close()

                if not reminders:
                    return ToolResult(text="No active reminders.", citations=[])

                lines = ["Active reminders:"]
                for r in reminders:
                    due_str = format_timestamp_local(r.due_at, r.timezone)
                    lines.append(f"  {r.id}. {r.message} (due: {due_str})")

                return ToolResult(text="\n".join(lines), citations=[])

            # Check for cancel command
            cancel_match = re.search(r'\b(cancel|delete|remove)\b.*\breminder\s+(\d+)', user_text, re.IGNORECASE)
            if cancel_match:
                reminder_id = int(cancel_match.group(2))
                store = ReminderStore(db_path)
                success = store.cancel_reminder(reminder_id)
                store.close()

                if success:
                    return ToolResult(text=f"Reminder {reminder_id} canceled.", citations=[])
                else:
                    return ToolResult(text=f"Could not cancel reminder {reminder_id} (not found or already sent).", citations=[])

            # Otherwise, try to create a reminder
            # Extract time and message
            # Patterns: "remind me to X at/in Y", "remind me at/in Y to X"
            patterns = [
                r'remind\s+(?:me\s+)?(?:to\s+)?(.+?)\s+(?:at|in)\s+(.+)',
                r'remind\s+(?:me\s+)?(?:at|in)\s+(.+?)\s+(?:to\s+)?(.+)',
            ]

            message = None
            time_expr = None

            for pattern in patterns:
                match = re.search(pattern, user_text, re.IGNORECASE)
                if match:
                    # Try both orderings
                    msg1, time1 = match.groups()
                    # Check which one looks more like a time expression
                    if re.search(r'\d+\s*(m|h|hour|min|am|pm|:\d+)', time1, re.IGNORECASE):
                        message = msg1.strip()
                        time_expr = time1.strip()
                    else:
                        message = time1.strip()
                        time_expr = msg1.strip()
                    break

            if not message or not time_expr:
                # Fallback: try to find any time expression and use the rest as message
                time_match = re.search(r'(?:in\s+\d+\s*\w+|at\s+\d+:\d+|tomorrow|next\s+\w+)', user_text, re.IGNORECASE)
                if time_match:
                    time_expr = time_match.group(0)
                    # Use the rest as message
                    message = user_text.replace(time_expr, '').replace('remind me', '').replace('to', '').strip()
                else:
                    return ToolResult(
                        text="Could not parse reminder. Please specify both a message and a time (e.g., 'remind me to call Bob in 2 hours').",
                        citations=[],
                    )

            # Parse the time
            timezone = os.getenv("TZ", "America/New_York")
            due_ts = parse_time_expression(time_expr, timezone=timezone)

            if due_ts is None:
                return ToolResult(
                    text=f"Could not parse time expression: '{time_expr}'. Try formats like 'in 2 hours', 'tomorrow at 9am', or '2026-01-15 14:30'.",
                    citations=[],
                )

            # Create the reminder
            store = ReminderStore(db_path)
            reminder_id = store.add_reminder(
                kind="REMIND",
                due_at=due_ts,
                message=message,
                timezone=timezone,
            )
            store.close()

            due_formatted = format_timestamp_local(due_ts, timezone)
            return ToolResult(
                text=f"✓ Reminder set (ID: {reminder_id})\n  Message: {message}\n  Due: {due_formatted}",
                citations=[],
            )

        except Exception as exc:
            logger.error(f"Reminder tool error: {exc}", exc_info=True)
            return ToolResult(text=f"Error creating reminder: {exc}", citations=[])

    def _parse_max_results(self, text: str, default: int = 3) -> int:
        match = re.search(r"\b(\d{1,2})\b", text)
        if match:
            try:
                value = int(match.group(1))
                return max(1, min(value, 10))
            except ValueError:
                return default
        return default

    def build_context(self, user_text: str, budget_tokens: int = 1200) -> ContextPacket:
        if not memory_enabled() or not user_text.strip():
            return ContextPacket(
                query=user_text,
                bullets=[],
                unknowns=["Memory disabled or empty request."],
                assumptions=[],
                kg_context=None,
            )

        # PhD-aware context building
        limit = int(os.getenv("MILTON_MEMORY_CONTEXT_LIMIT", "8"))

        # If PhD-related, prioritize PhD memories with lower recency bias
        if should_include_phd_context(user_text):
            recency_bias = float(os.getenv("MILTON_PHD_MEMORY_RECENCY_BIAS", "0.2"))
            limit = int(os.getenv("MILTON_PHD_MEMORY_CONTEXT_LIMIT", "12"))
        else:
            recency_bias = float(os.getenv("MILTON_MEMORY_RECENCY_BIAS", "0.35"))

        max_chars = int(os.getenv("MILTON_MEMORY_CONTEXT_MAX_CHARS", str(budget_tokens * 4)))

        # Use hybrid retrieval with semantic search
        memories = query_relevant_hybrid(
            user_text,
            limit=limit,
            recency_bias=recency_bias,
            semantic_weight=0.5,  # Balanced hybrid
            mode="hybrid",
        )

        # Record retrieval stats
        record_retrieval(query=user_text, count=len(memories), mode="hybrid")

        bullets: list[ContextBullet] = []
        current_chars = 0
        for item in memories:
            if not item.id:
                continue
            bullet_text = self._format_context_bullet(item)
            evidence_ids = [item.id]
            candidate = f"- {bullet_text} [evidence: {item.id}]"
            if current_chars + len(candidate) > max_chars:
                break
            bullets.append(ContextBullet(text=bullet_text, evidence_ids=evidence_ids))
            current_chars += len(candidate)

        unknowns: list[str] = []
        if not bullets:
            unknowns.append("No evidence-backed memory available for this request.")

        assumptions = ["Assume request is self-contained unless clarified."]

        # Add PhD context if relevant
        if should_include_phd_context(user_text):
            phd_ctx = get_phd_context(user_text, limit=5)

            # Add PhD bullets
            if phd_ctx.get("current_projects"):
                for proj in phd_ctx["current_projects"][:2]:
                    bullets.append(ContextBullet(
                        text=f"PhD Project: {proj[:200]}",
                        evidence_ids=["phd-profile"]
                    ))

            if phd_ctx.get("immediate_steps"):
                steps_text = "; ".join(phd_ctx["immediate_steps"][:3])
                bullets.append(ContextBullet(
                    text=f"PhD Immediate Steps: {steps_text[:200]}",
                    evidence_ids=["phd-profile"]
                ))

        # Build KG context (Phase 4)
        kg_context_text = None
        try:
            from agents.kg_context import build_kg_context
            kg_packet = build_kg_context(user_text, top_k=5)
            if not kg_packet.is_empty():
                kg_context_text = kg_packet.to_prompt_section()
                logger.debug(f"Added KG context: {len(kg_context_text)} chars")
        except Exception as e:
            logger.debug(f"KG context injection failed (gracefully continuing): {e}")

        return ContextPacket(
            query=user_text,
            bullets=bullets,
            unknowns=unknowns,
            assumptions=assumptions,
            kg_context=kg_context_text,
        )

    def _format_context_bullet(self, item: MemoryItem) -> str:
        content = " ".join(item.content.strip().split())
        if len(content) > 220:
            content = content[:217] + "..."
        tag_text = ", ".join(item.tags) if item.tags else "no-tags"
        return f"{content} (type={item.type}, tags={tag_text})"

    def _build_llm_prompt(self, user_text: str) -> str:
        return (
            "Use the context packet for grounding. "
            "Only reference memory when citing evidence ids from the packet. "
            "If the context is insufficient, ask a clarifying question.\n\n"
            f"User request: {user_text}"
        )

    def _safe_llm_call(
        self,
        user_text: str,
        context_packet: ContextPacket,
        system_prompt: Optional[str] = None,
    ) -> Optional[str]:
        try:
            prompt = self._build_llm_prompt(user_text)
            return self._call_llm(
                prompt,
                system_prompt=system_prompt or self.system_prompt,
                context_packet=context_packet,
            )
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            return None

    def _delegate_agent(
        self, agent_name: str, user_text: str, context_packet: ContextPacket
    ) -> Optional[str]:
        from agents import load_agent_context

        system_prompt = load_agent_context(agent_name)
        return self._safe_llm_call(
            user_text,
            context_packet=context_packet,
            system_prompt=system_prompt,
        )

    def route_request(
        self, user_text: str, context_packet: Optional[ContextPacket] = None
    ) -> RoutingDecision:
        """Route user request to an agent/tool using deterministic rules."""
        text = user_text.strip()
        context_ids = context_packet.context_ids if context_packet else []
        if not text:
            return RoutingDecision(
                route="nexus",
                rationale="Empty request; default to NEXUS.",
                context_ids=context_ids,
            )

        tool = self.tool_registry.match(text)
        if tool:
            return RoutingDecision(
                route="tool",
                rationale=f"Matched tool keywords for {tool.name}.",
                context_ids=context_ids,
                tool_name=tool.name,
            )

        lowered = text.lower()
        cortex_terms = (
            "write code",
            "implement",
            "build",
            "fix",
            "debug",
            "refactor",
            "run",
            "execute",
            "test",
            "benchmark",
        )
        if any(term in lowered for term in cortex_terms):
            return RoutingDecision(
                route="cortex",
                rationale="Execution-oriented request.",
                context_ids=context_ids,
            )

        frontier_terms = (
            "research",
            "scout",
            "monitor",
            "scan",
            "trend",
            "discover",
            "literature review",
        )
        if any(term in lowered for term in frontier_terms):
            return RoutingDecision(
                route="frontier",
                rationale="Research scouting request.",
                context_ids=context_ids,
            )

        return RoutingDecision(
            route="nexus",
            rationale="General request routed to NEXUS.",
            context_ids=context_ids,
        )

    def generate_morning_briefing(self) -> str:
        """
        Generate morning briefing with weather, news, calendar, and home status.

        Returns:
            Formatted morning briefing
        """
        logger.info("Generating morning briefing")

        sections = []

        # Header
        now = datetime.now()
        sections.append(f"Good morning, Cole! {now.strftime('%A, %B %d, %Y')}\n")
        sections.append("=" * 70 + "\n")

        # Weather
        try:
            weather_info = self.weather.format_current_weather()
            sections.append(f"\nWEATHER\n{weather_info}\n")
        except Exception as e:
            logger.error(f"Weather fetch failed: {e}")
            sections.append("\nWEATHER\nUnavailable\n")

        # Calendar (stub)
        sections.append("\nTODAY'S SCHEDULE\n")
        try:
            events = self.calendar.get_today_events()
            if events:
                sections.append(self.calendar.format_events(events))
            else:
                sections.append("No scheduled events\n")
        except Exception as e:
            sections.append("Calendar unavailable (stub implementation)\n")

        # News highlights
        sections.append("\nNEWS HIGHLIGHTS\n")
        try:
            headlines = self.news.get_top_headlines(category="technology", max_results=3)
            for i, article in enumerate(headlines, 1):
                sections.append(f"{i}. {article['title']} ({article['source']})\n")
        except Exception as e:
            logger.error(f"News fetch failed: {e}")
            sections.append("News unavailable\n")

        # Home status (if configured)
        sections.append("\nHOME STATUS\n")
        try:
            # Example: Check a temperature sensor
            # Replace with actual entity IDs
            sections.append("Home Assistant integration ready\n")
        except Exception:
            sections.append("Home Assistant unavailable\n")

        sections.append("\n" + "=" * 70)

        return "\n".join(sections)

    def generate_evening_briefing(self) -> str:
        """
        Generate evening briefing with day summary and overnight tasks.

        Returns:
            Formatted evening briefing
        """
        logger.info("Generating evening briefing")

        sections = []

        # Header
        sections.append(f"Evening briefing - {datetime.now().strftime('%A, %B %d')}\n")
        sections.append("=" * 70 + "\n")

        # Summary of day
        sections.append("\nDAY SUMMARY\n")
        sections.append("Tasks completed today: [To be implemented with memory system]\n")

        # Overnight queue status
        sections.append("\nOVERNIGHT QUEUE\n")
        sections.append("Scheduled jobs: [To be implemented with job queue]\n")

        # Tomorrow preview
        sections.append("\nTOMORROW\n")
        try:
            weather = self.weather.forecast(days=1)
            if weather and weather.get("days"):
                day = weather["days"][0]
                sections.append(
                    f"Weather: High {day['high']}°F, Low {day['low']}°F, {day['condition']}\n"
                )
        except Exception:
            sections.append("Weather forecast unavailable\n")

        sections.append("\n" + "=" * 70)

        return "\n".join(sections)

    def handle_bedtime(self, tasks: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Handle bedtime routine: queue overnight tasks, generate briefing.

        Args:
            tasks: List of tasks to queue for overnight processing

        Returns:
            Bedtime summary
        """
        logger.info("Handling bedtime routine")

        # Generate evening briefing
        briefing = self.generate_evening_briefing()

        # Queue tasks (placeholder)
        queued_tasks = tasks or []

        # Save briefing to inbox
        briefing_path = resolve_state_dir() / "inbox" / "evening" / (
            f"briefing_{datetime.now().strftime('%Y%m%d')}.txt"
        )

        try:
            os.makedirs(os.path.dirname(briefing_path), exist_ok=True)
            with open(briefing_path, "w") as f:
                f.write(briefing)
        except Exception as e:
            logger.error(f"Failed to save briefing: {e}")

        return {
            "briefing": briefing,
            "queued_tasks": queued_tasks,
            "briefing_saved": briefing_path,
        }

    def process_message(self, message: str) -> Response:
        """Process a user message through the deterministic NEXUS pipeline."""
        original_message = message
        reshaped_prompt_info: Optional[str] = None
        include_inspect = False
        is_trivial = True  # Default to trivial (no CoVe)
        pipeline_result = None

        # Run prompting pipeline if available and enabled
        if self._prompting_pipeline is not None:
            try:
                pipeline_result = self._prompting_pipeline.run(
                    message,
                    include_reshaped_prompt=True,  # Always compute, conditionally show
                )

                # Use reshaped prompt for downstream processing
                if pipeline_result.artifacts and pipeline_result.artifacts.prompt_spec:
                    spec = pipeline_result.artifacts.prompt_spec
                    if spec.was_modified():
                        message = spec.reshaped_prompt
                        logger.debug(f"Prompt reshaped: '{original_message[:50]}...' -> '{message[:50]}...'")

                # Store reshaped prompt info for potential inclusion in response
                if pipeline_result.reshaped_prompt:
                    reshaped_prompt_info = pipeline_result.reshaped_prompt
                    # Check if user explicitly requested to see the reshaped prompt
                    include_inspect = self._check_inspect_request(original_message)

                # Extract triviality from classification metadata
                if pipeline_result.artifacts and pipeline_result.artifacts.metadata:
                    classification = pipeline_result.artifacts.metadata.get("classification", {})
                    is_trivial = classification.get("is_trivial", True)

            except Exception as e:
                logger.warning(f"Prompting pipeline failed, using original message: {e}")

        context_packet = self.build_context(message)
        routing = self.route_request(message, context_packet=context_packet)
        context_ids = context_packet.context_ids

        route_label = routing.route
        citations: list[str] = []
        response_text: Optional[str] = None

        if routing.route == "tool":
            tool_name = routing.tool_name or "unknown"
            route_label = f"tool:{tool_name}"
            try:
                result = self.tool_registry.dispatch(tool_name, message)
                response_text = result.text
                citations = result.citations
            except Exception as exc:
                logger.error("Tool dispatch failed: %s", exc)
                response_text = (
                    f"Tool '{tool_name}' failed. "
                    "Check integration config or try again."
                )
        elif routing.route == "cortex":
            response_text = self._delegate_agent("CORTEX", message, context_packet)
        elif routing.route == "frontier":
            response_text = self._delegate_agent("FRONTIER", message, context_packet)
        else:
            response_text = self._safe_llm_call(message, context_packet)

        if response_text is None:
            response_text = (
                "LLM unavailable. Start vLLM with: python scripts/start_vllm.py "
                "and confirm LLM_API_URL is reachable."
            )

        # Run CoVe on non-trivial responses (config-gated)
        verified_badge: Optional[str] = None
        if (
            self._prompting_pipeline is not None
            and self._prompting_config is not None
            and self._prompting_config.enable_cove_for_responses
            and not is_trivial
        ):
            try:
                cove_result = self._prompting_pipeline.run(
                    response_text,
                    mode="full_answer",
                )
                response_text = cove_result.response
                verified_badge = cove_result.verified_badge
                logger.debug(f"Response verified with badge: {verified_badge}")
            except Exception as e:
                logger.warning(f"CoVe verification for response failed: {e}")

        # Append reshaped prompt info to response if user requested inspect
        if include_inspect and reshaped_prompt_info:
            response_text = f"{response_text}\n\n---\n{reshaped_prompt_info}"

        # Tag memory with PhD if relevant (use original message for memory)
        tags = ["request", f"route:{route_label}"]
        importance = 0.2

        if is_phd_related(original_message):
            tags.extend(["phd", "research"])
            importance = 0.4  # Higher importance for PhD-related messages

        # Record original user message to memory (not reshaped)
        record_memory(
            "NEXUS",
            original_message,
            memory_type="crumb",
            tags=tags,
            importance=importance,
            source="user",
        )
        if should_store_responses():
            record_memory(
                "NEXUS",
                response_text,
                memory_type="crumb",
                tags=["response", f"route:{route_label}"],
                importance=0.1,
                source="assistant",
            )

        return Response(
            text=response_text,
            citations=citations,
            route_used=route_label,
            context_used=context_ids,
            verified_badge=verified_badge,
            reshaped_from=reshaped_prompt_info if include_inspect else None,
        )

    def _check_inspect_request(self, message: str) -> bool:
        """Check if user requested to inspect the reshaped prompt."""
        text = message.strip().lower()
        return (
            "/show_prompt" in text
            or "/inspect_prompt" in text
            or text.endswith("inspect prompt")
            or text.endswith("show prompt")
            or text.endswith("show reshaped")
            or text.endswith("show reshaped prompt")
        )

    def _should_use_web_lookup(self, message: str, use_web: Optional[bool]) -> bool:
        if use_web is not None:
            return bool(use_web)
        if self.web_lookup_enabled:
            return True
        trigger_terms = ("source", "sources", "cite", "citation", "reference")
        return any(term in message.lower() for term in trigger_terms)

    def answer(
        self,
        message: str,
        use_web: Optional[bool] = None,
        one_way_mode: bool = False,
    ) -> str:
        """
        Answer a user message.

        Args:
            message: User's message
            use_web: Whether to use web lookup (None = auto-detect)
            one_way_mode: If True, enforce one-way channel mode (no clarification questions)

        Returns:
            Response text
        """
        # Build system prompt with optional one-way mode injection
        system_prompt = self.system_prompt
        if one_way_mode:
            system_prompt = f"{self.system_prompt}\n\n{ONE_WAY_PHONE_MODE_PROMPT}"
            logger.info("One-way phone mode enabled - clarification questions disabled")

        if self._should_use_web_lookup(message, use_web):
            response = self._answer_with_web_lookup(message, system_prompt=system_prompt)
        else:
            response = self._call_llm(message, system_prompt=system_prompt)

        # Post-generation guard for one-way mode
        if one_way_mode and detect_clarification_loop(response):
            logger.warning("Post-guard triggered: rewriting clarification-seeking response")
            response = rewrite_to_one_way_format(response, message)

        return response

    def answer_with_web_lookup(self, message: str) -> str:
        """Legacy wrapper for backward compatibility."""
        return self._answer_with_web_lookup(message, system_prompt=self.system_prompt)

    def _answer_with_web_lookup(self, message: str, system_prompt: str) -> str:
        """Internal web lookup implementation with configurable system prompt."""
        results = self.web_search.search(
            message, max_results=self.web_lookup_max_results
        )
        if not results:
            return self._call_llm(message, system_prompt=system_prompt)

        sources_block = "\n".join(
            f"[{i}] {item['title']} - {item['url']}"
            for i, item in enumerate(results, 1)
        )

        prompt = (
            "Answer the question using the web sources below. "
            "Cite sources inline like [1]. If the sources don't cover the "
            "claim, say you couldn't verify it.\n\n"
            f"Question: {message}\n\nSources:\n{sources_block}"
        )
        response = self._call_llm(prompt, system_prompt=system_prompt)

        if "Sources:" not in response:
            response = f"{response.strip()}\n\nSources:\n{sources_block}"
        return response


if __name__ == "__main__":
    # Simple test
    nexus = NEXUS()
    print("NEXUS agent initialized")
    print("\nGenerating morning briefing...\n")
    print(nexus.generate_morning_briefing())
