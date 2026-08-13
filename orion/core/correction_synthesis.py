"""Assimilates accumulated corrections into a compact "lessons learned"
digest, the same way core/consolidation.py folds aging chat history into a
running summary.

log_correction captures individual mistakes as they happen (see
tools/correction_tool.py), but a long-lived assistant will eventually log
dozens of them — dumping all of them raw into every system prompt doesn't
scale, and buries genuinely repeated patterns ("I keep defaulting to the
wrong calendar") inside one-off corrections. Once more than
SYNTHESIZE_THRESHOLD corrections have accumulated since the last synthesis,
the oldest overflow gets folded into a running digest via one extra Claude
call, merged with whatever was already synthesized before — mirroring
Consolidator's CONSOLIDATE_THRESHOLD/KEEP_RECENT split exactly.
"""
from __future__ import annotations

from typing import Callable

import anthropic

from core.memory import Correction, Memory

CorrectionSummarizer = Callable[[str, list[Correction]], str]

SYNTHESIZE_THRESHOLD = 12
KEEP_RECENT = 6

_SYNTHESIZE_PROMPT = """You maintain a compact "lessons learned" digest for a personal AI assistant, built \
from corrections its user has given it over time. Update the digest below to incorporate the new \
corrections, keeping it compact (a few short bullet points at most): merge similar or repeated \
corrections into one general rule, drop anything superseded by a later correction, and phrase each \
point as a concrete instruction for next time rather than a description of the past mistake. Write \
only the updated digest, nothing else.

EXISTING DIGEST:
{previous_digest}

NEW CORRECTIONS TO INCORPORATE:
{new_corrections}"""


def make_default_correction_summarizer(client: anthropic.Anthropic, model: str) -> CorrectionSummarizer:
    def summarize(previous_digest: str, new_corrections: list[Correction]) -> str:
        transcript = "\n".join(
            f"[{c.category}] mistake: {c.mistake} | correction: {c.correction}"
            + (f" | context: {c.context}" if c.context else "")
            for c in new_corrections
        )
        prompt = _SYNTHESIZE_PROMPT.format(
            previous_digest=previous_digest or "(none yet)", new_corrections=transcript
        )
        response = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return "\n".join(b.text for b in response.content if b.type == "text").strip()

    return summarize


class CorrectionSynthesizer:
    def __init__(self, memory: Memory, summarize: CorrectionSummarizer):
        self._memory = memory
        self._summarize = summarize

    def maybe_synthesize(self) -> None:
        consolidated_through = self._memory.get_corrections_consolidated_through()
        pending = self._memory.corrections_after(consolidated_through)
        if len(pending) <= SYNTHESIZE_THRESHOLD:
            return

        to_synthesize = pending[: len(pending) - KEEP_RECENT]
        if not to_synthesize:
            return

        previous_digest = self._memory.get_corrections_digest()
        new_digest = self._summarize(previous_digest, to_synthesize)
        self._memory.set_corrections_digest(new_digest, to_synthesize[-1].id)
