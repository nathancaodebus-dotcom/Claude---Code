"""interfaces/cli.py's REPL loop. Regression coverage for a real bug found
during a full-codebase audit: unlike every other interface (voice_loop.py's
run() loop, web/app.py's _stream_chat), the call to agent.respond() here had
no try/except around it — any exception other than the specific ones
core/agent.py itself already falls back to Ollama for (a SQLite hiccup, a
malformed tool schema, anything unexpected) took down the whole CLI process
and lost the session, instead of just failing that one turn."""
from __future__ import annotations

import builtins

import pytest

import interfaces.cli as cli_module
from core.config import config


class _FakeAgent:
    def __init__(self, *args, **kwargs):
        self.calls: list[str] = []
        self.fail_on: set[str] = set()

    def respond(self, session_id: str, message: str) -> str:
        self.calls.append(message)
        if message in self.fail_on:
            raise RuntimeError("boom")
        return f"echo: {message}"


@pytest.fixture
def cli_env(monkeypatch, tmp_path):
    original_api_key = config.anthropic_api_key
    object.__setattr__(config, "anthropic_api_key", "test-key")
    monkeypatch.setattr(cli_module, "purge_old_outputs", lambda *a, **k: None)
    monkeypatch.setattr(cli_module, "Memory", lambda: object())
    monkeypatch.setattr(cli_module, "Store", lambda: object())
    monkeypatch.setattr(cli_module, "build_registry", lambda memory, store: object())

    fake_agent = _FakeAgent()
    monkeypatch.setattr(cli_module, "Agent", lambda memory, registry: fake_agent)

    # Real schedulers against a throwaway store would work fine (nothing to
    # poll), but a no-op stand-in keeps this test fast and independent of
    # core/scheduler.py's/core/health_monitor.py's own thread timing.
    class _NoopBackgroundTask:
        def __init__(self, *a, **k):
            pass

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(cli_module, "ReminderScheduler", _NoopBackgroundTask)
    monkeypatch.setattr(cli_module, "HealthMonitor", _NoopBackgroundTask)
    yield fake_agent
    object.__setattr__(config, "anthropic_api_key", original_api_key)


def _run_cli_with_inputs(monkeypatch, inputs: list[str]) -> list[str]:
    remaining = iter(inputs)
    printed: list[str] = []

    def fake_input(prompt: str = "") -> str:
        try:
            return next(remaining)
        except StopIteration:
            raise EOFError from None

    def fake_print(*args, **kwargs):
        printed.append(" ".join(str(a) for a in args))

    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(cli_module, "print", fake_print, raising=False)
    cli_module.main()
    return printed


def test_a_failed_turn_prints_an_error_and_the_loop_continues(cli_env, monkeypatch):
    cli_env.fail_on = {"trigger failure"}

    printed = _run_cli_with_inputs(monkeypatch, ["trigger failure", "hello", "exit"])

    assert cli_env.calls == ["trigger failure", "hello"]  # the loop kept going after the failure
    assert any("went wrong" in line for line in printed)
    assert any("echo: hello" in line for line in printed)


def test_a_successful_turn_still_prints_the_reply_normally(cli_env, monkeypatch):
    printed = _run_cli_with_inputs(monkeypatch, ["hi there", "exit"])

    assert cli_env.calls == ["hi there"]
    assert any("echo: hi there" in line for line in printed)
