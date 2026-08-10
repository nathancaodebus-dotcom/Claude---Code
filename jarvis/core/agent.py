"""The Jarvis agent loop: one Claude tool-use loop shared by every interface
(CLI, Telegram, voice). Interfaces only ever call `Agent.respond()`."""
from __future__ import annotations

import anthropic

from core.config import config
from core.memory import Memory
from tools.base import ToolRegistry

SYSTEM_PROMPT_TEMPLATE = """You are {name}, the user's personal AI assistant — a second self they can \
ask for absolutely anything, at any time: answering questions, managing email, managing their \
calendar, controlling devices in their home, or just talking things through.

Be direct, warm, and efficient — like a trusted right hand, not a customer-support bot. Use tools \
proactively instead of asking the user to do things themselves when a tool can do it. If a request \
is ambiguous in a way that changes the outcome (e.g. which light, which event to cancel), ask a \
short clarifying question instead of guessing. If you don't have a tool for something, say so plainly.

{facts_block}"""

MAX_TOOL_ITERATIONS = 8


class Agent:
    def __init__(self, memory: Memory, tools: ToolRegistry):
        self._memory = memory
        self._tools = tools
        self._client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    def _system_prompt(self) -> str:
        return SYSTEM_PROMPT_TEMPLATE.format(
            name=config.assistant_name,
            facts_block=self._memory.facts_as_prompt_block(),
        )

    def respond(self, session_id: str, user_message: str) -> str:
        self._memory.append(session_id, "user", user_message)

        messages = [
            {"role": m.role, "content": m.content} for m in self._memory.history(session_id)
        ]

        final_text = ""
        for _ in range(MAX_TOOL_ITERATIONS):
            response = self._client.messages.create(
                model=config.model,
                max_tokens=2048,
                system=self._system_prompt(),
                tools=self._tools.anthropic_schemas(),
                messages=messages,
            )

            text_blocks = [b.text for b in response.content if b.type == "text"]
            final_text = "\n".join(text_blocks).strip()

            if response.stop_reason != "tool_use":
                break

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = self._tools.dispatch(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        self._memory.append(session_id, "assistant", final_text)
        return final_text
