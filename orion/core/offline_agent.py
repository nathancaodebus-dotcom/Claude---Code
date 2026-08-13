"""Local fallback reasoning for when Claude is genuinely unreachable — no
internet, an Anthropic outage, or an empty account balance. Talks to a
locally running Ollama server instead, exposing only the tools that make
no network call of their own (Tool.requires_network in tools/base.py) —
there's no point offering a Gmail or weather tool a local model can't
reach either, and every such tool would just fail loudly mid-conversation.

This is a fallback, not a replacement: an open-weight local model is
meaningfully less reliable at multi-step tool orchestration than Claude
(see the comparison discussed with the user — this project deliberately
doesn't try to replace Claude as the default reasoning engine anywhere
else, and this is no exception). core/agent.py only ever reaches for this
after a real Claude call fails for a specifically offline-shaped reason,
never on its own initiative — and every offline reply is prefixed so it's
never ambiguous which "brain" actually answered.
"""
from __future__ import annotations

from typing import Any

import httpx

from core.config import config
from tools.base import ToolRegistry

OFFLINE_REPLY_PREFIX = "[mode hors-ligne] "

SYSTEM_PROMPT = """You are {name}, currently running in offline fallback mode: the usual cloud \
model is unreachable (no internet connection, or the account is temporarily out of API credit), so \
a smaller local model is answering instead. If asked why you seem different or more limited, say so \
plainly. Only a small set of tools that need no internet access are available right now — to-dos, \
notes, reminders, remembered facts, local documents/spreadsheets/presentations, local file/image/video \
edits, and similar. If the user asks for something that needs email, calendar, music, weather, web \
search, or any other online service, say clearly that it needs an internet connection and isn't \
available until the connection (or account) is back — never pretend, guess, or make up an answer."""

MAX_TOOL_ITERATIONS = 6
_REQUEST_TIMEOUT_S = 120


def is_ollama_reachable(host: str, timeout: float = 2.0) -> bool:
    try:
        response = httpx.get(f"{host.rstrip('/')}/api/tags", timeout=timeout)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


class OfflineAgent:
    def __init__(self, tools: ToolRegistry, host: str, model: str):
        self._tools = tools
        self._host = host.rstrip("/")
        self._model = model

    def _tool_schemas(self) -> list[dict[str, Any]]:
        return [t.to_ollama_schema() for t in self._tools.offline_safe_tools()]

    def respond(self, user_message: str) -> str:
        """Deliberately single-turn: Claude's conversation history is
        shaped for the Anthropic API (content blocks, tool_use/tool_result
        entries) and isn't safely reusable here, so a fallback reply
        answers just the message that triggered it rather than pretending
        to carry over full context across a mode switch it can't actually
        see."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(name=config.assistant_name)},
            {"role": "user", "content": user_message},
        ]

        final_text = ""
        for _ in range(MAX_TOOL_ITERATIONS):
            response = httpx.post(
                f"{self._host}/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "tools": self._tool_schemas(),
                    "stream": False,
                },
                timeout=_REQUEST_TIMEOUT_S,
            )
            response.raise_for_status()
            message = response.json()["message"]

            final_text = message.get("content") or final_text
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                break

            messages.append(message)
            for call in tool_calls:
                fn = call["function"]
                result = self._tools.dispatch(fn["name"], fn.get("arguments") or {})
                messages.append({"role": "tool", "content": result})

        return OFFLINE_REPLY_PREFIX + final_text
