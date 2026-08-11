"""Measures real end-to-end response latency against your actual
ANTHROPIC_API_KEY — the sandbox this project was built in has no API key of
its own, so these numbers can only come from a run on real hardware (this
Pi, your PC, wherever .env is filled in).

What it measures, and why each one matters:

1. Simple question, no tool needed — the floor: pure Claude latency with
   nothing else added. This is what "as fast as typing into Google" is
   actually being compared against.
2. A question that needs a live lookup (weather) — every tool call means a
   *second* full round trip to Claude (first call decides to use the tool,
   the tool runs, then a second call turns the result into an answer), on
   top of however long the tool itself takes. This is usually the real gap
   between "feels instant" and "feels like it's thinking."
3. The same simple question run twice in one session — shows prompt
   caching (added earlier this project) actually paying off: the second
   call should look measurably cheaper/faster than the first, since the
   system prompt + tool schemas get reused instead of reprocessed.

For each, it reports:
- time to first sentence (when TTS could start speaking, thanks to
  streaming) — the number that actually matters for how fast a voice
  reply *feels*.
- total time to the full answer.

Usage:
    cd orion && source .venv/bin/activate
    python -m scripts.benchmark_latency
"""
from __future__ import annotations

import statistics
import time

from core.agent import Agent
from core.config import config
from core.memory import Memory
from core.store import Store
from tools.registry_builder import build_registry

SESSION_ID = "benchmark"


def _time_one_call(agent: Agent, session_id: str, prompt: str) -> tuple[float, float, str]:
    """Returns (seconds_to_first_sentence, seconds_to_full_reply, reply)."""
    start = time.perf_counter()
    first_sentence_at: list[float] = []

    def on_sentence(_text: str) -> None:
        if not first_sentence_at:
            first_sentence_at.append(time.perf_counter())

    reply = agent.respond_streaming(session_id, prompt, on_sentence=on_sentence)
    end = time.perf_counter()

    time_to_first = (first_sentence_at[0] - start) if first_sentence_at else (end - start)
    return time_to_first, end - start, reply


def _report(label: str, runs: list[tuple[float, float, str]]) -> None:
    first_times = [r[0] for r in runs]
    total_times = [r[1] for r in runs]
    print(f"\n{label}")
    print(f"  time to first sentence : {statistics.mean(first_times):.2f}s (of {len(runs)} run(s))")
    print(f"  time to full reply     : {statistics.mean(total_times):.2f}s")
    print(f"  reply (last run)       : {runs[-1][2][:150]}{'...' if len(runs[-1][2]) > 150 else ''}")


def main() -> None:
    if not config.anthropic_api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set — this benchmark makes real API calls and "
            "needs your real key in .env, same as running Orion itself."
        )

    memory = Memory(db_path=":memory:")
    store = Store(db_path=":memory:")
    agent = Agent(memory, build_registry(memory, store))

    print(f"Benchmarking against model: {config.model}")
    print("Each scenario is one real Claude API call — this will take a little while.\n")

    simple_runs = [
        _time_one_call(agent, SESSION_ID, "Quelle est la capitale de l'Australie ?")
    ]
    _report("1. Simple question, no tool call", simple_runs)

    tool_runs = [
        _time_one_call(agent, SESSION_ID, "Quel temps fait-il à Genève actuellement ?")
    ]
    _report("2. Question needing a live tool call (weather)", tool_runs)

    cached_runs = [
        _time_one_call(agent, "benchmark-cache-2", "Quelle est la capitale du Japon ?"),
        _time_one_call(agent, "benchmark-cache-2", "Quelle est la capitale du Brésil ?"),
    ]
    _report(
        "3. Two simple questions in the same session (2nd should benefit from prompt caching)",
        cached_runs,
    )
    print(
        f"\n  -> call 1: {cached_runs[0][1]:.2f}s total, call 2: {cached_runs[1][1]:.2f}s total"
    )


if __name__ == "__main__":
    main()
