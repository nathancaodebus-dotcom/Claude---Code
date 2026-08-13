"""Lets the model log a mistake and what to do instead, distinct from
remember_fact: facts are durable things that are true (preferences,
routines), corrections are specifically about behavior that went wrong so
it can be actively avoided next time — see core/correction_synthesis.py for
how these get folded into a "lessons learned" digest over time, and
core/agent.py's SYSTEM_PROMPT_STATIC for when the model is told to use
this over/alongside remember_fact."""
from __future__ import annotations

from core.memory import Memory
from core.vector_memory import VectorMemory
from tools.base import Tool


class LogCorrectionTool(Tool):
    requires_network = False
    name = "log_correction"
    description = (
        "Log a mistake you made and what to do instead, whenever the user corrects how you did "
        "something (wrong tone, wrong assumption, wrong tool choice, a wrong default, a rule for "
        "next time). Use this instead of remember_fact for corrections specifically — it's reviewed "
        "and distilled into general 'lessons learned' over time instead of just sitting as one more "
        "fact. Suggested categories: tool_usage, factual, tone, scheduling, preference, other."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Short category label, e.g. 'tool_usage', 'tone', 'factual', 'scheduling'.",
            },
            "mistake": {"type": "string", "description": "What you did or said that was wrong."},
            "correction": {"type": "string", "description": "What you should do instead, next time."},
            "context": {
                "type": "string",
                "description": "Optional short context, e.g. which tool/topic this happened with.",
            },
        },
        "required": ["category", "mistake", "correction"],
    }

    def __init__(self, memory: Memory, vector_memory: VectorMemory | None = None):
        self._memory = memory
        self._vector_memory = vector_memory

    def run(self, category: str, mistake: str, correction: str, context: str = "") -> str:
        self._memory.log_correction(category, mistake, correction, context)
        if self._vector_memory is not None:
            # Also indexed into semantic memory so search_memory can surface
            # this correction contextually when a related topic comes up
            # later, not just via the digest's bounded recap.
            self._vector_memory.index(
                f"Correction ({category}): {mistake} -> instead, {correction}", source="correction"
            )
        return f"Logged correction [{category}]: {mistake} -> {correction}"


class ListCorrectionsTool(Tool):
    requires_network = False
    name = "list_corrections"
    description = "List recently logged corrections and the current 'lessons learned' digest, if any."
    input_schema = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Max corrections to return. Default 20."},
        },
    }

    def __init__(self, memory: Memory):
        self._memory = memory

    def run(self, limit: int = 20) -> str:
        digest = self._memory.get_corrections_digest()
        recent = self._memory.recent_corrections(limit)

        parts = []
        if digest:
            parts.append(f"Lessons learned digest:\n{digest}")
        if recent:
            lines = "\n".join(
                f"- [{c.category}] {c.mistake} -> {c.correction}" for c in recent
            )
            parts.append(f"Recent corrections:\n{lines}")
        return "\n\n".join(parts) if parts else "No corrections logged yet."
