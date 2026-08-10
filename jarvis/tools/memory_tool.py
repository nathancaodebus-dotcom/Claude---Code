"""Lets the model save durable facts about the user ('remember this')."""
from __future__ import annotations

from core.memory import Memory
from tools.base import Tool


class RememberFactTool(Tool):
    name = "remember_fact"
    description = (
        "Save a durable fact about the user for future conversations (preferences, "
        "recurring context, people, routines...). Use this whenever the user shares "
        "something worth remembering long-term, not for one-off details."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Short identifier for the fact, e.g. 'favorite_coffee' or 'dog_name'.",
            },
            "value": {"type": "string", "description": "The fact itself."},
        },
        "required": ["key", "value"],
    }

    def __init__(self, memory: Memory):
        self._memory = memory

    def run(self, key: str, value: str) -> str:
        self._memory.remember_fact(key, value)
        return f"Remembered: {key} = {value}"


class RecallFactsTool(Tool):
    name = "recall_facts"
    description = "List every durable fact previously remembered about the user."
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, memory: Memory):
        self._memory = memory

    def run(self) -> str:
        return self._memory.facts_json()
