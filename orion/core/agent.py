"""The Orion agent loop: one Claude tool-use loop shared by every interface
(CLI, Telegram, voice). Interfaces only ever call `Agent.respond()` (or
`Agent.respond_streaming()` for one that wants to react to the reply as it's
generated, e.g. to start speaking before the full text is ready)."""
from __future__ import annotations

import re
import threading
from typing import Any, Callable

import anthropic

from core.config import config
from core.consolidation import Consolidator, make_default_summarizer
from core.memory import Memory
from tools.base import ToolRegistry

# Static instructions only — never changes across users, sessions, or turns,
# which is what makes it worth prompt-caching (see _system_blocks below).
# Per-user facts/summary are appended as a separate, uncached block.
SYSTEM_PROMPT_STATIC = """You are {name}, the user's personal AI assistant — a second self they can \
ask for absolutely anything, at any time: answering questions, managing email, managing their \
calendar, controlling devices in their home, generating and editing documents (PowerPoint, Word, \
Excel), playing music and video, or just talking things through. Requests arrive as dictated speech \
as often as text, so expect informal, run-on phrasing and resolve it into the right tool call rather \
than asking the user to rephrase. Your full name is O.R.I.O.N. — Omniscient Reconnaissance & \
Intelligence Network — but you go by {name} day to day; only spell it out if the user actually asks \
what it stands for.

Be direct, warm, and efficient — like a trusted right hand, not a customer-support bot. Use tools \
proactively instead of asking the user to do things themselves when a tool can do it. If a request \
is ambiguous in a way that changes the outcome (e.g. which light, which event to cancel), ask a \
short clarifying question instead of guessing. If you don't have a tool for something, say so plainly.

Learn continuously, don't just wait to be told to remember something: call remember_fact whenever you \
notice a durable fact, preference, routine, or correction — not just when the user explicitly says \
'remember this'. If the user corrects how you did something (wrong tone, wrong assumption, a rule for \
next time), store that correction as a fact so you don't repeat the mistake. Check recall_facts if you're \
about to do something the user might have already told you a preference about.

When you create a document (presentation/Word doc/spreadsheet), remember the document_name you get \
back — later requests like 'add a slide about X' or 'change the second bullet' refer back to that \
same document without the user repeating its name, so track it from context.

Casting: launch_app_on_tv can open Netflix, Disney+, Spotify, or YouTube on the TV, but only YouTube \
supports jumping straight to a specific video (play_youtube_video) — for Netflix/Disney+ say clearly \
that you've opened the app and the user will need to pick the title themselves, don't imply you chose it.

Some capabilities are duplicated across a built-in version and an external service (to-dos vs. Todoist, \
notes vs. Obsidian) — if both are available and the user hasn't said which they mean, ask once, then \
remember the answer as a preference so you don't ask again.

Crypto trading tools are research and paper-tracking only — there is no connection to a real exchange, \
and propose_crypto_trade never executes anything by itself. After proposing a trade, tell the user what \
you'd do and why, then explicitly ask them to confirm or reject it — never say a trade is 'done' until \
they've confirmed it and confirm_crypto_trade has actually run. Never call confirm_crypto_trade on your \
own initiative, no matter how confident you are in the analysis."""

MAX_TOOL_ITERATIONS = 8

# Chunk streamed text into sentences at ., !, ?, or … followed by whitespace,
# so a voice interface can start synthesizing/speaking each sentence as soon
# as it's complete instead of waiting for the whole reply.
_SENTENCE_END_RE = re.compile(r"[.!?…]+(?:\s+|$)")


class Agent:
    def __init__(self, memory: Memory, tools: ToolRegistry):
        self._memory = memory
        self._tools = tools
        self._client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        self._consolidator = Consolidator(
            memory, make_default_summarizer(self._client, config.fast_model)
        )

    def _system_blocks(self, session_id: str) -> list[dict[str, Any]]:
        static_text = SYSTEM_PROMPT_STATIC.format(name=config.assistant_name)
        blocks = [
            {"type": "text", "text": static_text, "cache_control": {"type": "ephemeral"}}
        ]

        dynamic_text = "\n\n".join(
            block
            for block in (
                self._memory.facts_as_prompt_block(),
                self._memory.summary_as_prompt_block(session_id),
            )
            if block
        )
        if dynamic_text:
            blocks.append({"type": "text", "text": dynamic_text})
        return blocks

    def _cached_tool_schemas(self) -> list[dict[str, Any]]:
        """Marks a cache breakpoint after the tool definitions (by far the
        largest and most stable part of every request — over a hundred tool
        schemas that never change between calls) so Claude reuses them
        instead of reprocessing the full list on every single turn."""
        schemas = self._tools.anthropic_schemas()
        if not schemas:
            return schemas
        schemas = list(schemas)
        schemas[-1] = {**schemas[-1], "cache_control": {"type": "ephemeral"}}
        return schemas

    def respond(self, session_id: str, user_message: str) -> str:
        return self.respond_streaming(session_id, user_message, on_sentence=None)

    def respond_streaming(
        self,
        session_id: str,
        user_message: str,
        on_sentence: Callable[[str], None] | None,
    ) -> str:
        """Runs the same tool-use loop as respond(), but streams the final
        answer and calls on_sentence(text) as each sentence completes,
        instead of only returning once the whole reply is done. Pass None
        for on_sentence to just get the full text back, as respond() does."""
        self._memory.append(session_id, "user", user_message)

        messages = [
            {"role": m.role, "content": m.content} for m in self._memory.history(session_id)
        ]

        final_text = ""
        for _ in range(MAX_TOOL_ITERATIONS):
            buffer = ""
            with self._client.messages.stream(
                model=config.model,
                # Generation is sequential — every output token adds directly to
                # response latency, so this stays only as large as a fast,
                # conversational reply actually needs (~750 words). If a single
                # turn genuinely needs more (a long document via a tool call's
                # arguments, say), the tool-use loop above already continues
                # across iterations rather than needing one huge one.
                max_tokens=1024,
                system=self._system_blocks(session_id),
                tools=self._cached_tool_schemas(),
                messages=messages,
            ) as stream:
                for delta in stream.text_stream:
                    buffer += delta
                    if on_sentence is not None:
                        while (match := _SENTENCE_END_RE.search(buffer)) is not None:
                            on_sentence(buffer[: match.end()].strip())
                            buffer = buffer[match.end():]
                response = stream.get_final_message()

            if on_sentence is not None and buffer.strip():
                on_sentence(buffer.strip())

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
        # maybe_consolidate is a no-op almost every turn (a cheap row count
        # check) but, once a session crosses CONSOLIDATE_THRESHOLD messages,
        # makes a full extra Claude call to rewrite the summary — running
        # that inline would silently tack an entire second API round trip
        # onto whichever response happens to cross the threshold. Memory's
        # SQLite connections are already opened with check_same_thread=False
        # for exactly this kind of cross-thread use, so it's safe to fire
        # this in the background and return the user's answer immediately.
        threading.Thread(
            target=self._consolidator.maybe_consolidate, args=(session_id,), daemon=True
        ).start()
        return final_text
