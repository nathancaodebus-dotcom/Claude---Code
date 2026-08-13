"""interfaces/web/app.py's FastAPI routes. Follows the same fake-agent
pattern already established in shopping-assistant/tests/test_app.py:
monkeypatch the module-level _agent (constructed once at import time, same
as every other interface's shared Agent) rather than rebuilding the app per
test."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from interfaces.web import app as app_module


@pytest.fixture
def client():
    with TestClient(app_module.app) as c:
        yield c


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        assert block.startswith("data: ")
        events.append(json.loads(block[len("data: "):]))
    return events


class _FakeAgent:
    def __init__(self, sentences: list[str], final_text: str | None = None, error: Exception | None = None):
        self._sentences = sentences
        self._final_text = final_text if final_text is not None else " ".join(sentences)
        self._error = error
        self.calls: list[tuple[str, str]] = []

    def respond_streaming(self, session_id, message, on_sentence):
        self.calls.append((session_id, message))
        if self._error:
            raise self._error
        for s in self._sentences:
            on_sentence(s)
        return self._final_text


def test_status_reports_assistant_name_and_model(client):
    response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["assistant_name"]
    assert body["model"]
    assert body["ready"] is True  # conftest.py sets a truthy ANTHROPIC_API_KEY


def test_index_serves_the_hud_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "O.R.I.O.N." in response.text


def test_static_assets_are_served(client):
    assert client.get("/style.css").status_code == 200
    assert client.get("/app.js").status_code == 200


def test_chat_streams_each_sentence_then_a_done_event(client, monkeypatch):
    fake_agent = _FakeAgent(["Bonjour.", "Comment puis-je aider ?"])
    monkeypatch.setattr(app_module, "_agent", fake_agent)

    response = client.post("/api/chat", json={"message": "salut"})

    events = _parse_sse(response.text)
    assert events[0] == {"type": "sentence", "text": "Bonjour."}
    assert events[1] == {"type": "sentence", "text": "Comment puis-je aider ?"}
    assert events[2]["type"] == "done"
    assert events[2]["text"] == "Bonjour. Comment puis-je aider ?"
    assert fake_agent.calls == [(app_module.SESSION_ID, "salut")]


def test_chat_done_event_includes_drained_attachments(client, monkeypatch):
    from core import attachments

    def fake_respond(session_id, message, on_sentence):
        attachments.push("outputs/images/test.png")
        return "voilà l'image"

    fake_agent = _FakeAgent([])
    fake_agent.respond_streaming = fake_respond
    monkeypatch.setattr(app_module, "_agent", fake_agent)

    response = client.post("/api/chat", json={"message": "génère une image"})

    events = _parse_sse(response.text)
    done_event = events[-1]
    assert done_event["type"] == "done"
    assert done_event["attachments"] == ["outputs/images/test.png"]


def test_chat_rejects_empty_message_without_calling_the_agent(client, monkeypatch):
    fake_agent = _FakeAgent(["should not be reached"])
    monkeypatch.setattr(app_module, "_agent", fake_agent)

    response = client.post("/api/chat", json={"message": "   "})

    events = _parse_sse(response.text)
    assert events == [{"type": "error", "text": "Empty message."}]
    assert fake_agent.calls == []


def test_chat_surfaces_agent_exceptions_as_an_error_event(client, monkeypatch):
    fake_agent = _FakeAgent([], error=RuntimeError("Claude is unreachable"))
    monkeypatch.setattr(app_module, "_agent", fake_agent)

    response = client.post("/api/chat", json={"message": "salut"})

    events = _parse_sse(response.text)
    assert events == [{"type": "error", "text": "Claude is unreachable"}]


def test_chat_rejects_a_second_concurrent_request_for_the_same_session(client, monkeypatch):
    """FastAPI runs sync path operations in a thread pool, so two open tabs
    (or a rapid double-send) posting to /api/chat at once would otherwise
    race Agent.respond_streaming's read-history/append-message sequence
    against each other and can corrupt the shared conversation. Simulates
    'a request is already in flight' by holding the session lock directly,
    then checks a second request is rejected cleanly instead of proceeding."""
    lock = app_module._chat_lock(app_module.SESSION_ID)
    lock.acquire()
    try:
        fake_agent = _FakeAgent(["should not be reached"])
        monkeypatch.setattr(app_module, "_agent", fake_agent)

        response = client.post("/api/chat", json={"message": "salut"})

        events = _parse_sse(response.text)
        assert events == [
            {
                "type": "error",
                "text": "Orion is still answering the previous message — wait for it to finish.",
            }
        ]
        assert fake_agent.calls == []
    finally:
        lock.release()


def test_chat_lock_is_released_after_completion_allowing_the_next_request(client, monkeypatch):
    fake_agent = _FakeAgent(["ok"])
    monkeypatch.setattr(app_module, "_agent", fake_agent)

    first = client.post("/api/chat", json={"message": "un"})
    second = client.post("/api/chat", json={"message": "deux"})

    assert _parse_sse(first.text)[-1]["type"] == "done"
    assert _parse_sse(second.text)[-1]["type"] == "done"
    assert fake_agent.calls == [(app_module.SESSION_ID, "un"), (app_module.SESSION_ID, "deux")]


def test_chat_lock_is_released_after_an_error_allowing_the_next_request(client, monkeypatch):
    monkeypatch.setattr(app_module, "_agent", _FakeAgent([], error=RuntimeError("boom")))
    client.post("/api/chat", json={"message": "un"})

    monkeypatch.setattr(app_module, "_agent", _FakeAgent(["ok"]))
    second = client.post("/api/chat", json={"message": "deux"})

    assert _parse_sse(second.text)[-1]["type"] == "done"


def test_outputs_mount_serves_generated_files(client):
    # The mount is registered against the real outputs/ dir at import time
    # (same directory every generation tool writes to, and the same
    # relative path attachments.drain() returns) — write a real file there
    # rather than monkeypatching _OUTPUTS_DIR, which the already-registered
    # StaticFiles mount wouldn't pick up anyway.
    marker = app_module._OUTPUTS_DIR / "test_web_app_marker.txt"
    marker.write_text("hi")
    try:
        response = client.get("/outputs/test_web_app_marker.txt")
        assert response.status_code == 200
        assert response.text == "hi"
    finally:
        marker.unlink()


def test_outputs_mount_404s_for_a_missing_file(client):
    response = client.get("/outputs/does-not-exist.png")
    assert response.status_code == 404
