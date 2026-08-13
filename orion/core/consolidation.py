"""Assimilates aging conversation history into a durable per-session summary.

Memory.history() only ever sends the most recent messages to the model —
anything older just falls out of context and is effectively forgotten, even
though it's still sitting in the database. This closes that gap: once a
session accumulates more than CONSOLIDATE_THRESHOLD messages, the oldest
overflow (everything except the most recent KEEP_RECENT, which matches
Memory.history's own default window) gets folded into a running summary via
one extra Claude call, merged with whatever was already summarized before.
The summary is then always included in the system prompt, so the assistant
keeps the gist of a long relationship even once the raw messages are gone
from the active context.
"""
from __future__ import annotations

from typing import Callable

import anthropic

from core.memory import Memory, Message

Summarizer = Callable[[str, list[Message]], str]

CONSOLIDATE_THRESHOLD = 60
KEEP_RECENT = 40

_SUMMARIZE_PROMPT = """You maintain a running memory digest of an ongoing conversation between a \
personal AI assistant and its user. Update the digest below to incorporate the new exchange, keeping \
it compact (a few short paragraphs or bullet points at most): preserve durable, useful context — \
topics discussed, decisions made, ongoing tasks, things that matter for future conversations — and \
drop small talk and anything already superseded. Write only the updated digest, nothing else.

EXISTING DIGEST:
{previous_summary}

NEW EXCHANGE TO INCORPORATE:
{new_messages}"""


def make_default_summarizer(client: anthropic.Anthropic, model: str) -> Summarizer:
    def summarize(previous_summary: str, new_messages: list[Message]) -> str:
        transcript = "\n".join(f"{m.role}: {m.content}" for m in new_messages)
        prompt = _SUMMARIZE_PROMPT.format(
            previous_summary=previous_summary or "(none yet)", new_messages=transcript
        )
        response = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return "\n".join(b.text for b in response.content if b.type == "text").strip()

    return summarize


class Consolidator:
    def __init__(self, memory: Memory, summarize: Summarizer):
        self._memory = memory
        self._summarize = summarize

    def maybe_consolidate(self, session_id: str) -> None:
        consolidated_through = self._memory.get_consolidated_through(session_id)
        pending = self._memory.messages_after(session_id, consolidated_through)
        if len(pending) <= CONSOLIDATE_THRESHOLD:
            return

        to_summarize = pending[: len(pending) - KEEP_RECENT]
        if not to_summarize:
            return

        previous_summary = self._memory.get_summary(session_id)
        new_summary = self._summarize(previous_summary, to_summarize)
        self._memory.set_summary(session_id, new_summary, to_summarize[-1].id)
