"""interfaces/web/app.py's request-hardening additions, found during a
full-codebase audit: no auth/CSRF defense (multipart/form-data is a
CORS-safelisted content type, so /api/transcribe was reachable via a
hidden auto-submitting form on any site the owner had open, with no
preflight), no upload/message size caps."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from interfaces.web import app as app_module


@pytest.fixture
def client():
    with TestClient(app_module.app) as c:
        yield c


# --- Origin check (CSRF defense) --------------------------------------


def test_chat_rejects_a_mismatched_origin(client):
    response = client.post(
        "/api/chat", json={"message": "hi"}, headers={"origin": "https://evil.example"}
    )
    assert response.status_code == 403


def test_transcribe_rejects_a_mismatched_origin(client):
    response = client.post(
        "/api/transcribe", files={"audio": ("clip.webm", b"fake-audio", "audio/webm")},
        headers={"origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_chat_allows_a_matching_localhost_origin(client, monkeypatch):
    monkeypatch.setattr(app_module, "_agent", _FakeAgentForOrigin())
    response = client.post(
        "/api/chat", json={"message": "hi"}, headers={"origin": "http://127.0.0.1:8420"}
    )
    assert response.status_code == 200


def test_chat_allows_a_missing_origin_header(client, monkeypatch):
    """No Origin header at all is the non-browser case (curl, a local
    script) -- already the trusted baseline this loopback-only process
    assumes, so it must not be blocked."""
    monkeypatch.setattr(app_module, "_agent", _FakeAgentForOrigin())
    response = client.post("/api/chat", json={"message": "hi"})
    assert response.status_code == 200


class _FakeAgentForOrigin:
    def respond_streaming(self, session_id, message, on_sentence):
        on_sentence("ok")
        return "ok"


# --- request body size cap ----------------------------------------------


def test_oversized_request_body_is_rejected(client):
    oversized = b"x" * (app_module._MAX_REQUEST_BODY_BYTES + 1)
    response = client.post(
        "/api/transcribe", files={"audio": ("clip.webm", oversized, "audio/webm")}
    )
    assert response.status_code == 413


def test_a_normal_sized_upload_is_not_rejected_by_the_size_cap(client):
    small = b"x" * 1024
    response = client.post("/api/transcribe", files={"audio": ("clip.webm", small, "audio/webm")})
    # Whatever faster-whisper/transcription does with fake bytes isn't the
    # point here -- only that the size middleware doesn't reject it.
    assert response.status_code != 413


# --- chat message length cap ---------------------------------------------


def test_overlong_chat_message_is_rejected():
    with TestClient(app_module.app) as client:
        overlong = "a" * (app_module._MAX_CHAT_MESSAGE_CHARS + 1)
        response = client.post("/api/chat", json={"message": overlong})
        assert response.status_code == 422


def test_chat_message_at_the_length_cap_is_accepted(monkeypatch):
    monkeypatch.setattr(app_module, "_agent", _FakeAgentForOrigin())
    with TestClient(app_module.app) as client:
        at_cap = "a" * app_module._MAX_CHAT_MESSAGE_CHARS
        response = client.post("/api/chat", json={"message": at_cap})
        assert response.status_code == 200


# --- _verify_same_origin unit tests (no HTTP round trip needed) ---------


class _FakeRequest:
    def __init__(self, origin: str | None):
        self.headers = {"origin": origin} if origin is not None else {}


def test_verify_same_origin_accepts_127_0_0_1():
    app_module._verify_same_origin(_FakeRequest("http://127.0.0.1:8420"))  # must not raise


def test_verify_same_origin_accepts_localhost():
    app_module._verify_same_origin(_FakeRequest("http://localhost:8420"))  # must not raise


def test_verify_same_origin_rejects_other_hosts():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        app_module._verify_same_origin(_FakeRequest("https://evil.example"))
    assert exc_info.value.status_code == 403
