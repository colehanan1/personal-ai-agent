"""Tool registry for NEXUS integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any


@dataclass(frozen=True)
class ToolResult:
    text: str
    citations: list[str] = field(default_factory=list)
    data: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    keywords: tuple[str, ...]
    handler: Callable[[str], ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition, replace: bool = True) -> None:
        if not replace and tool.name in self._tools:
            return
        self._tools[tool.name] = tool

    def has(self, name: str) -> bool:
        return name in self._tools

    def match(self, text: str) -> Optional[ToolDefinition]:
        lowered = text.lower()
        for tool in self._tools.values():
            if any(keyword in lowered for keyword in tool.keywords):
                return tool
        return None

    def dispatch(self, tool_name: str, user_text: str) -> ToolResult:
        if tool_name not in self._tools:
            raise ValueError(f"Tool not registered: {tool_name}")
        return self._tools[tool_name].handler(user_text)

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())


_REGISTRY = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    return _REGISTRY


def register_tool(tool: ToolDefinition, replace: bool = True) -> None:
    _REGISTRY.register(tool, replace=replace)
