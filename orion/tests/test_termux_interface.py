import subprocess

import pytest

from interfaces.termux.orion_termux import MAX_TURNS_PER_SESSION, run_conversation


class FakeAgent:
    def __init__(self):
        self.calls = []

    def respond(self, session_id, text):
        self.calls.append(text)
        return f"reply to: {text}"


def _mock_run(transcripts):
    """Returns a fake subprocess.run that answers termux-speech-to-text calls
    in sequence and no-ops everything else."""
    state = {"i": 0}

    def fake_run(cmd, **kwargs):
        if cmd[0] == "termux-speech-to-text":
            text = transcripts[state["i"]] if state["i"] < len(transcripts) else ""
            state["i"] += 1
            return subprocess.CompletedProcess(cmd, 0, stdout=text, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    return fake_run


def test_conversation_ends_on_silence(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _mock_run(["hello there"]))
    agent = FakeAgent()

    run_conversation(agent)

    assert agent.calls == ["hello there"]


def test_conversation_ends_on_stop_phrase(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _mock_run(["what's the weather", "stop"]))
    agent = FakeAgent()

    run_conversation(agent)

    assert agent.calls == ["what's the weather"]


def test_conversation_continues_across_multiple_turns(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _mock_run(["turn one", "turn two", "turn three", ""]))
    agent = FakeAgent()

    run_conversation(agent)

    assert agent.calls == ["turn one", "turn two", "turn three"]


def test_conversation_caps_at_max_turns(monkeypatch):
    transcripts = [f"turn {i}" for i in range(MAX_TURNS_PER_SESSION + 5)]
    monkeypatch.setattr(subprocess, "run", _mock_run(transcripts))
    agent = FakeAgent()

    run_conversation(agent)

    assert len(agent.calls) == MAX_TURNS_PER_SESSION


def test_immediate_silence_makes_no_agent_calls(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _mock_run([""]))
    agent = FakeAgent()

    run_conversation(agent)

    assert agent.calls == []
