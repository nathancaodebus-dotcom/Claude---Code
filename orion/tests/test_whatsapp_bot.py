"""interfaces/whatsapp_bot.py's webhook handling, signature verification,
and message dispatch. Follows the same fake-agent pattern as
tests/test_web_app.py, plus a fake httpx client standing in for
core.http.client so no real Graph API calls happen."""
from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import interfaces.whatsapp_bot as whatsapp_bot
from core import attachments
from core.config import config


# --- shared fixtures ---------------------------------------------------


@pytest.fixture(autouse=True)
def _whatsapp_config():
    attachments.drain()  # ensure a clean slate regardless of what earlier tests left queued
    fields = {
        "whatsapp_app_secret": "test-app-secret",
        "whatsapp_allowed_number": "41791234567",
        "whatsapp_verify_token": "test-verify-token",
        "whatsapp_phone_number_id": "123456",
        "whatsapp_access_token": "test-access-token",
    }
    originals = {name: getattr(config, name) for name in fields}
    for name, value in fields.items():
        object.__setattr__(config, name, value)
    yield
    for name, value in originals.items():
        object.__setattr__(config, name, value)


def _sign(body: bytes, secret: str = "test-app-secret") -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class _FakeAgent:
    def __init__(self, reply: str = "ok"):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []
        self.error: Exception | None = None

    def respond(self, session_id: str, message: str) -> str:
        self.calls.append((session_id, message))
        if self.error:
            raise self.error
        return self.reply


class _FakeResponse:
    def __init__(self, json_data=None, content=b"", status_code=200):
        self._json_data = json_data or {}
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=httpx.Response(self.status_code))

    def json(self):
        return self._json_data


class _FakeHttpClient:
    def __init__(self):
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[str] = []
        self.media_response = _FakeResponse({"url": "https://cdn.example/media", "mime_type": "audio/ogg"})
        self.download_response = _FakeResponse(content=b"fake-audio-bytes")
        self.upload_response = _FakeResponse({"id": "uploaded-media-id"})

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if url.endswith("/media"):
            return self.upload_response
        return _FakeResponse({"messages": [{"id": "wamid.fake"}]})

    def get(self, url, **kwargs):
        self.gets.append(url)
        if "cdn.example" in url:
            return self.download_response
        return self.media_response


@pytest.fixture
def fake_client(monkeypatch):
    fake = _FakeHttpClient()
    monkeypatch.setattr(whatsapp_bot, "client", fake)
    return fake


# --- signature verification ---------------------------------------------


def test_verify_signature_accepts_a_correctly_signed_body():
    body = b'{"hello": "world"}'
    assert whatsapp_bot._verify_webhook_signature(body, _sign(body)) is True


def test_verify_signature_rejects_a_wrong_signature():
    body = b'{"hello": "world"}'
    assert whatsapp_bot._verify_webhook_signature(body, _sign(b"different body")) is False


def test_verify_signature_rejects_a_missing_header():
    assert whatsapp_bot._verify_webhook_signature(b"body", None) is False


def test_verify_signature_rejects_a_malformed_header():
    assert whatsapp_bot._verify_webhook_signature(b"body", "not-sha256-prefixed") is False


def test_verify_signature_fails_closed_without_a_configured_secret():
    object.__setattr__(config, "whatsapp_app_secret", None)
    body = b'{"hello": "world"}'
    # Even a signature that *would* be valid for some secret must fail
    # when none is configured -- fail closed, not "skip verification".
    assert whatsapp_bot._verify_webhook_signature(body, _sign(body)) is False


# --- owner authorization --------------------------------------------------


def test_is_authorized_matches_normalized_numbers():
    assert whatsapp_bot._is_authorized("41791234567") is True
    assert whatsapp_bot._is_authorized("+41 79 123 45 67") is True


def test_is_authorized_rejects_other_numbers():
    assert whatsapp_bot._is_authorized("15550001111") is False


def test_is_authorized_fails_closed_without_a_configured_number():
    object.__setattr__(config, "whatsapp_allowed_number", None)
    assert whatsapp_bot._is_authorized("41791234567") is False


# --- message handlers (direct unit tests) ---------------------------------


def test_handle_text_message_sends_the_agent_reply(fake_client):
    agent = _FakeAgent(reply="Hello there!")

    whatsapp_bot._handle_text_message(agent, "41791234567", "hi")

    assert agent.calls == [("whatsapp", "hi")]
    urls = [url for url, _ in fake_client.posts]
    assert any(url.endswith("/messages") for url in urls)
    sent_bodies = [kwargs["json"] for url, kwargs in fake_client.posts if url.endswith("/messages")]
    assert sent_bodies[0]["text"]["body"] == "Hello there!"
    assert sent_bodies[0]["to"] == "41791234567"


def test_handle_text_message_reports_a_failure_instead_of_vanishing_silently(fake_client):
    """Regression test for a real bug found during a full-codebase audit:
    agent.respond() used to run unguarded here -- a transient Anthropic
    error or an uncaught tool exception meant the inbound message just
    vanished with no reply and no error shown to the owner."""
    agent = _FakeAgent()
    agent.error = RuntimeError("boom")

    whatsapp_bot._handle_text_message(agent, "41791234567", "hi")

    sent_bodies = [kwargs["json"] for url, kwargs in fake_client.posts if url.endswith("/messages")]
    assert len(sent_bodies) == 1
    assert "went wrong" in sent_bodies[0]["text"]["body"]


def test_handle_unsupported_message_explains_the_limitation(fake_client):
    whatsapp_bot._handle_unsupported_message("41791234567", "image")

    sent_bodies = [kwargs["json"] for url, kwargs in fake_client.posts if url.endswith("/messages")]
    assert "image" in sent_bodies[0]["text"]["body"]


def test_handle_audio_message_transcribes_and_replies(fake_client, monkeypatch):
    agent = _FakeAgent(reply="The weather is nice.")
    monkeypatch.setattr(whatsapp_bot, "_transcribe", lambda path: "what's the weather")

    whatsapp_bot._handle_audio_message(agent, None, "41791234567", "media-123")

    assert agent.calls == [("whatsapp", "what's the weather")]
    sent_bodies = [kwargs["json"] for url, kwargs in fake_client.posts if url.endswith("/messages")]
    assert "The weather is nice." in sent_bodies[0]["text"]["body"]
    assert "what's the weather" in sent_bodies[0]["text"]["body"]


def test_handle_audio_message_reports_a_failure_instead_of_vanishing_silently(fake_client, monkeypatch):
    agent = _FakeAgent()
    agent.error = RuntimeError("boom")
    monkeypatch.setattr(whatsapp_bot, "_transcribe", lambda path: "what's the weather")

    whatsapp_bot._handle_audio_message(agent, None, "41791234567", "media-123")

    sent_bodies = [kwargs["json"] for url, kwargs in fake_client.posts if url.endswith("/messages")]
    assert len(sent_bodies) == 1
    assert "went wrong" in sent_bodies[0]["text"]["body"]


def test_handle_audio_message_reports_when_transcription_is_unconfident(fake_client, monkeypatch):
    agent = _FakeAgent()
    monkeypatch.setattr(whatsapp_bot, "_transcribe", lambda path: "")

    whatsapp_bot._handle_audio_message(agent, None, "41791234567", "media-123")

    assert agent.calls == []
    sent_bodies = [kwargs["json"] for url, kwargs in fake_client.posts if url.endswith("/messages")]
    assert "Didn't catch that" in sent_bodies[0]["text"]["body"]


def test_handle_audio_message_reports_when_stt_is_unavailable(fake_client, monkeypatch):
    agent = _FakeAgent()
    monkeypatch.setattr(whatsapp_bot, "_transcribe", lambda path: None)

    whatsapp_bot._handle_audio_message(agent, None, "41791234567", "media-123")

    assert agent.calls == []
    sent_bodies = [kwargs["json"] for url, kwargs in fake_client.posts if url.endswith("/messages")]
    assert "requirements-voice.txt" in sent_bodies[0]["text"]["body"]


def test_handle_audio_message_reports_a_failed_download(fake_client, monkeypatch):
    agent = _FakeAgent()
    monkeypatch.setattr(whatsapp_bot, "_download_media", lambda media_id: None)

    whatsapp_bot._handle_audio_message(agent, None, "41791234567", "media-123")

    assert agent.calls == []
    sent_bodies = [kwargs["json"] for url, kwargs in fake_client.posts if url.endswith("/messages")]
    assert "download" in sent_bodies[0]["text"]["body"].lower()


def test_process_message_ignores_unauthorized_senders(fake_client):
    agent = _FakeAgent()

    whatsapp_bot._process_message(agent, None, {"from": "10000000000", "type": "text", "text": {"body": "hi"}})

    assert agent.calls == []
    assert fake_client.posts == []


# --- FastAPI routes (webhook verification + dispatch) ----------------------


@pytest.fixture
def app_client(fake_client):
    from core.store import Store

    agent = _FakeAgent(reply="Hello from Orion.")
    store = Store(db_path=":memory:")
    app = whatsapp_bot.build_app(agent, store, tts=None)
    with TestClient(app) as c:
        c.agent = agent
        yield c


def test_get_webhook_returns_the_challenge_when_verified(app_client):
    response = app_client.get(
        "/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "12345"},
    )
    assert response.status_code == 200
    assert response.text == "12345"


def test_get_webhook_rejects_a_wrong_verify_token(app_client):
    response = app_client.get(
        "/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"},
    )
    assert response.status_code == 403


def test_post_webhook_rejects_an_unsigned_request(app_client):
    body = json.dumps({"entry": []}).encode()
    response = app_client.post("/webhook", content=body, headers={"content-type": "application/json"})
    assert response.status_code == 403
    assert app_client.agent.calls == []


def test_post_webhook_processes_a_signed_text_message(app_client, fake_client):
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{"from": "41791234567", "type": "text", "text": {"body": "hi Orion"}}]
                }
            }]
        }]
    }
    body = json.dumps(payload).encode()
    response = app_client.post(
        "/webhook",
        content=body,
        headers={"content-type": "application/json", "x-hub-signature-256": _sign(body)},
    )

    assert response.status_code == 200
    assert app_client.agent.calls == [("whatsapp", "hi Orion")]
    sent_bodies = [kwargs["json"] for url, kwargs in fake_client.posts if url.endswith("/messages")]
    assert sent_bodies[0]["text"]["body"] == "Hello from Orion."


def test_post_webhook_ignores_status_update_payloads(app_client, fake_client):
    """WhatsApp also posts delivery-status updates (sent/delivered/read) to
    the same webhook, under "statuses" instead of "messages" -- these must
    not be mistaken for an inbound message and answered."""
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]}
    body = json.dumps(payload).encode()
    response = app_client.post(
        "/webhook",
        content=body,
        headers={"content-type": "application/json", "x-hub-signature-256": _sign(body)},
    )

    assert response.status_code == 200
    assert app_client.agent.calls == []
    assert fake_client.posts == []
