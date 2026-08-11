"""Base class + registry for agent tools.

Every integration (Gmail, Calendar, Home Assistant, ...) implements one
`Tool` subclass. The agent loop never knows about specific integrations —
it only talks to the registry, so adding a new capability to Orion means
adding one file here and registering it, nothing in core/agent.py changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


class Tool(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]

    @abstractmethod
    def run(self, **kwargs: Any) -> str:
        """Execute the tool and return a string result to feed back to the model."""
        raise NotImplementedError

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    def __init__(self, on_failure: Callable[[str, str], None] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self._on_failure = on_failure

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def anthropic_schemas(self) -> list[dict[str, Any]]:
        return [t.to_anthropic_schema() for t in self._tools.values()]

    def dispatch(self, name: str, kwargs: dict[str, Any]) -> str:
        tool = self.get(name)
        if tool is None:
            error = f"Error: unknown tool '{name}'."
            self._log_failure(name, error)
            return error
        try:
            return tool.run(**kwargs)
        except Exception as exc:  # noqa: BLE001 - tool errors must surface to the model, not crash the loop
            error = f"Error running tool '{name}': {exc}"
            self._log_failure(name, error)
            return error

    def _log_failure(self, name: str, error: str) -> None:
        if self._on_failure is not None:
            self._on_failure(name, error)
