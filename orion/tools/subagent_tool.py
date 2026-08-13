"""Delegate a sub-task to a specialized one-shot Claude call — a 'research
agent', 'code agent', or 'writer agent' with a narrower system prompt than
the main assistant, useful for breaking a big ask ('prepare a comparative
report on X') into focused pieces without cluttering the main conversation
with intermediate work.

This is a single non-tool-using call (the sub-agent doesn't get Orion's
tools — it reasons over what it's given), which keeps it simple and cheap.
For sub-tasks that need tools too, the main agent should just call those
tools itself instead of delegating.
"""
from __future__ import annotations

import anthropic

from core.config import config
from tools.base import Tool

_ROLE_PROMPTS = {
    "researcher": (
        "You are a research specialist. Given a topic or question and any provided context, "
        "produce a thorough, well-organized brief: key facts, different angles, and open questions. "
        "Be precise about what's established fact vs. your own inference."
    ),
    "coder": (
        "You are a coding specialist. Given a task and any provided context, write clean, correct, "
        "minimal code with a short explanation of the approach. Flag any assumptions you had to make."
    ),
    "writer": (
        "You are a writing specialist. Given a topic, audience, and any provided material, produce "
        "clear, well-structured prose in the requested format and tone."
    ),
    "critic": (
        "You are a critical reviewer playing devil's advocate. Given an idea or plan, find its "
        "weakest assumptions, logical gaps, and the strongest counter-arguments — be genuinely "
        "adversarial, not just polite hedging."
    ),
}


class DelegateToSubagentTool(Tool):
    name = "delegate_to_subagent"
    description = (
        "Delegate a focused sub-task to a specialized one-shot assistant: 'researcher' (gather/"
        "organize information), 'coder' (write code), 'writer' (draft prose), or 'critic' (stress-test "
        "an idea, devil's advocate). Use this to break a large request into pieces rather than doing "
        "everything in one pass — e.g. for 'prepare a comparative report on X', delegate research, "
        "then delegate writing the final draft from the research output."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "role": {"type": "string", "enum": list(_ROLE_PROMPTS.keys())},
            "task": {"type": "string", "description": "What the sub-agent should do."},
            "context": {"type": "string", "description": "Any background/material it needs."},
        },
        "required": ["role", "task"],
    }

    def __init__(self):
        self._client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    def run(self, role: str, task: str, context: str = "") -> str:
        user_content = task if not context else f"{task}\n\nContext:\n{context}"
        response = self._client.messages.create(
            model=config.model,
            max_tokens=2048,
            system=_ROLE_PROMPTS[role],
            messages=[{"role": "user", "content": user_content}],
        )
        return "\n".join(b.text for b in response.content if b.type == "text").strip()
