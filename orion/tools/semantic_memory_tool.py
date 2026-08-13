"""Tool wrapper around core/vector_memory.py: index things worth recalling
by meaning later, and search for them the same way — 'what did I say about
the Peterson project a while back' rather than an exact keyword match."""
from __future__ import annotations

from core.vector_memory import VectorMemory
from tools.base import Tool


class IndexMemoryTool(Tool):
    requires_network = False
    name = "index_memory"
    description = (
        "Save a piece of information into long-term semantic memory, so it can be found later "
        "by meaning even if the user's wording is completely different. Use this for things "
        "worth being able to recall months later by topic — beyond what remember_fact's short "
        "key/value facts cover (e.g. the substance of a discussion, a decision and its reasoning)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "source": {"type": "string", "description": "Short label for where this came from, e.g. 'conversation', 'email'."},
        },
        "required": ["text"],
    }

    def __init__(self, vector_memory: VectorMemory):
        self._memory = vector_memory

    def run(self, text: str, source: str = "conversation") -> str:
        self._memory.index(text, source)
        return "Indexed into long-term memory."


class SearchMemoryTool(Tool):
    requires_network = False
    name = "search_memory"
    description = (
        "Search long-term semantic memory for anything related to a topic, by meaning rather "
        "than exact wording — use this when trying to recall something from a while ago."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "description": "Default 5."},
        },
        "required": ["query"],
    }

    def __init__(self, vector_memory: VectorMemory):
        self._memory = vector_memory

    def run(self, query: str, max_results: int = 5) -> str:
        matches = self._memory.search(query, top_k=max_results)
        if not matches:
            return "No related memories found."
        return "\n".join(f"- ({m.source}, relevance {m.score:.2f}) {m.text}" for m in matches)
