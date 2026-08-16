"""WhatsApp interface via Meta's official WhatsApp Cloud API — webhook-based
rather than the long-polling python-telegram-bot uses for the Telegram
interface (interfaces/telegram_bot.py), since that's how the Cloud API
works: Meta POSTs inbound messages to a webhook URL you register, and
replies go out through the Graph API. Restricted to a single owner phone
number, same reasoning as Telegram's single-owner-id restriction — this is
a private assistant, not a public bot, even though the webhook URL itself
has to be reachable from the internet.

Voice notes get transcribed and answered with a spoken reply too, reusing
the exact same TTS backend (core/tts.py) and OGG/Opus encoding path
(core/tts.py's synthesize_to_ogg_opus, shared with interfaces/telegram_bot.py)
Telegram voice messages use — WhatsApp's audio message type accepts the
same OGG/Opus container Telegram voice notes do.

Every inbound webhook POST is authenticated via the X-Hub-Signature-256
header (HMAC-SHA256 over the raw body, keyed by the Meta App Secret) before
anything in the body — including the sender's phone number, which is what
the owner-only check relies on — is trusted. Skipping that check would let
anyone who finds the webhook URL POST a fake message claiming to be from
the owner's number and have it treated as a real command.

Setup is real infrastructure, not just an API key: a Meta Developer app,
a WhatsApp Business phone number, and a webhook URL Meta can reach over
HTTPS (a reverse proxy or tunnel in front of this process, since it only
binds locally) — see README §21 for the full walkthrough.

Reminders and health alerts push proactively the same way Telegram's do,
but with an important WhatsApp-specific limitation: the Cloud API only
allows free-form, business-initiated messages within the 24-hour window
after the owner last messaged Orion. Outside that window, an unprompted
push needs a pre-approved message template, which this project doesn't
set up. In practice that means proactive pushes work fine as long as
there's been a real conversation in the last 24h, and silently stop
working (logged, not crashed) if the owner hasn't spoken to Orion in a
while — reopening the window (just saying hi) is what makes them resume.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
import uvicorn
from fastapi import BackgroundTasks, FastAPI, Request, Response

from core import attachments
from core.agent import Agent
from core.config import config
from core.health_monitor import HealthMonitor
from core.http import client
from core.logging_setup import configure_logging
from core.memory import Memory
from core.outputs_cleanup import purge_old_outputs
from core.scheduler import ReminderScheduler
from core.stt import join_confident_segments
from core.store import Store
from core.tts import Synthesizer, get_synthesizer_if_available, synthesize_to_ogg_opus
from tools.registry_builder import build_registry

logger = logging.getLogger("orion.whatsapp")

SESSION_ID = "whatsapp"
_GRAPH_TIMEOUT_S = 15.0
_MEDIA_TIMEOUT_S = 30.0

_whisper_model = None
_whisper_model_lock = threading.Lock()


def _get_whisper_model():
    """Same lazily-loaded, cached-singleton pattern interfaces/web/app.py
    uses (a couple of seconds to load — not worth paying per message)."""
    global _whisper_model
    with _whisper_model_lock:
        if _whisper_model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                return None
            _whisper_model = WhisperModel(config.whisper_model_size, device="cpu", compute_type="int8")
        return _whisper_model


def _transcribe(audio_path: Path) -> str | None:
    model = _get_whisper_model()
    if model is None:
        return None
    segments, _ = model.transcribe(str(audio_path), language=config.voice_language)
    return join_confident_segments(segments)


def _normalize_number(number: str) -> str:
    return "".join(ch for ch in number if ch.isdigit())


def _is_authorized(from_number: str) -> bool:
    if not config.whatsapp_allowed_number:
        logger.warning("WHATSAPP_ALLOWED_NUMBER is not set — refusing all messages for safety.")
        return False
    return _normalize_number(from_number) == _normalize_number(config.whatsapp_allowed_number)


def _verify_webhook_signature(body: bytes, signature_header: str | None) -> bool:
    """Meta signs every webhook POST with the App Secret; this rejects a
    request that isn't actually from Meta before anything in the body
    (including the sender number the owner-only check below relies on)
    gets trusted. Fails closed: no configured secret means no request
    passes, not "skip verification"."""
    if not config.whatsapp_app_secret:
        logger.error("WHATSAPP_APP_SECRET is not set — refusing all webhook requests for safety.")
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(config.whatsapp_app_secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, provided)


def _graph_url(path: str) -> str:
    return f"https://graph.facebook.com/{config.whatsapp_api_version}/{path}"


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {config.whatsapp_access_token}"}


def _send_text(to: str, text: str) -> None:
    response = client.post(
        _graph_url(f"{config.whatsapp_phone_number_id}/messages"),
        headers=_auth_headers(),
        json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}},
        timeout=_GRAPH_TIMEOUT_S,
    )
    response.raise_for_status()


def _send_media_message(to: str, media_type: str, media_id: str, extra: dict[str, Any] | None = None) -> None:
    payload = {"messaging_product": "whatsapp", "to": to, "type": media_type, media_type: {"id": media_id, **(extra or {})}}
    response = client.post(
        _graph_url(f"{config.whatsapp_phone_number_id}/messages"),
        headers=_auth_headers(),
        json=payload,
        timeout=_GRAPH_TIMEOUT_S,
    )
    response.raise_for_status()


def _upload_media(content: bytes, mime_type: str, filename: str) -> str:
    response = client.post(
        _graph_url(f"{config.whatsapp_phone_number_id}/media"),
        headers=_auth_headers(),
        data={"messaging_product": "whatsapp", "type": mime_type},
        files={"file": (filename, content, mime_type)},
        timeout=_MEDIA_TIMEOUT_S,
    )
    response.raise_for_status()
    return response.json()["id"]


def _download_media(media_id: str) -> tuple[bytes, str] | None:
    """Two-step fetch the Graph API requires: resolve the media id to a
    short-lived CDN URL, then download from that URL — both requests need
    the same bearer token, the second one isn't a public URL. Returns None
    (rather than raising) on any failure, since a failed download of one
    voice message shouldn't take the whole webhook handler down."""
    try:
        meta_response = client.get(_graph_url(media_id), headers=_auth_headers(), timeout=_GRAPH_TIMEOUT_S)
        meta_response.raise_for_status()
        meta = meta_response.json()

        content_response = client.get(meta["url"], headers=_auth_headers(), timeout=_MEDIA_TIMEOUT_S)
        content_response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Failed to download WhatsApp media %s: %s", media_id, exc)
        return None
    return content_response.content, meta.get("mime_type", "application/octet-stream")


def _send_voice_reply(tts: Synthesizer, to: str, text: str, urgent: bool = False) -> None:
    ogg_bytes = synthesize_to_ogg_opus(tts, text, urgent=urgent)
    if not ogg_bytes:
        return
    media_id = _upload_media(ogg_bytes, "audio/ogg; codecs=opus", "reply.ogg")
    _send_media_message(to, "audio", media_id)


def _send_attachments(to: str) -> None:
    for path in attachments.drain():
        content = Path(path).read_bytes()
        name = Path(path).name
        if name.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
            mime_type = "image/png" if name.lower().endswith(".png") else "image/jpeg"
            media_id = _upload_media(content, mime_type, name)
            _send_media_message(to, "image", media_id)
        else:
            media_id = _upload_media(content, "application/octet-stream", name)
            _send_media_message(to, "document", media_id, extra={"filename": name})


def _try_send_text(to: str, text: str) -> None:
    """Every outbound send in this module goes through here so a failed
    Graph API call (expired token, rate limit, the owner outside the 24h
    free-form window) gets logged instead of crashing the background task
    that's processing this one inbound message."""
    try:
        _send_text(to, text)
    except httpx.HTTPStatusError as exc:
        logger.warning("Failed to send WhatsApp reply to %s: %s", to, exc)


def _respond_or_report_failure(agent: Agent, from_number: str, text: str) -> str | None:
    """agent.respond() used to run unguarded here -- a transient Anthropic
    error or an uncaught tool exception meant the inbound message just
    vanished with no reply and no error shown to the owner, unlike every
    outbound Graph API call in this module (which all go through
    _try_send_text and degrade the same way). Found during a full-codebase
    audit. Returns None (having already told the owner) on failure, so
    callers can just check for that instead of duplicating the try/except."""
    try:
        return agent.respond(SESSION_ID, text)
    except Exception as exc:  # noqa: BLE001 - must degrade to a visible message, never vanish silently
        logger.exception("agent.respond() failed for a WhatsApp message from %s: %s", from_number, exc)
        _try_send_text(from_number, "Something went wrong on my end — try again?")
        return None


def _handle_text_message(agent: Agent, from_number: str, text: str) -> None:
    reply = _respond_or_report_failure(agent, from_number, text)
    if reply is None:
        return
    _try_send_text(from_number, reply)
    try:
        _send_attachments(from_number)
    except httpx.HTTPStatusError as exc:
        logger.warning("Failed to send WhatsApp attachment to %s: %s", from_number, exc)


def _handle_audio_message(agent: Agent, tts: Synthesizer | None, from_number: str, media_id: str) -> None:
    downloaded = _download_media(media_id)
    if downloaded is None:
        _try_send_text(from_number, "Couldn't download that voice message — could you send it again?")
        return
    content, _mime_type = downloaded

    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_path = Path(tmp_dir) / "voice.ogg"
        audio_path.write_bytes(content)
        transcript = _transcribe(audio_path)

    if transcript is None:
        _try_send_text(
            from_number,
            "I can't transcribe voice messages yet — install requirements-voice.txt "
            "(faster-whisper) to enable it, or send text for now.",
        )
        return
    if not transcript:
        _try_send_text(from_number, "Didn't catch that — could you send it again?")
        return

    reply = _respond_or_report_failure(agent, from_number, transcript)
    if reply is None:
        return
    _try_send_text(from_number, f"\U0001f3a4 “{transcript}”\n\n{reply}")
    try:
        if tts is not None:
            _send_voice_reply(tts, from_number, reply)
        _send_attachments(from_number)
    except httpx.HTTPStatusError as exc:
        logger.warning("Failed to send WhatsApp voice reply/attachment to %s: %s", from_number, exc)


def _handle_unsupported_message(from_number: str, message_type: str) -> None:
    _try_send_text(
        from_number,
        f"I can only read text and voice messages on WhatsApp right now — {message_type} isn't supported yet.",
    )


def _process_message(agent: Agent, tts: Synthesizer | None, message: dict[str, Any]) -> None:
    from_number = message.get("from", "")
    if not _is_authorized(from_number):
        logger.warning("Ignoring WhatsApp message from unauthorized number.")
        return

    message_type = message.get("type")
    if message_type == "text":
        _handle_text_message(agent, from_number, message["text"]["body"])
    elif message_type == "audio":
        _handle_audio_message(agent, tts, from_number, message["audio"]["id"])
    else:
        _handle_unsupported_message(from_number, message_type or "this")


def build_app(agent: Agent, store: Store, tts: Synthesizer | None) -> FastAPI:
    def _notify_reminder(text: str) -> None:
        _send_text(config.whatsapp_allowed_number, f"⏰ Reminder: {text}")
        if tts is not None:
            _send_voice_reply(tts, config.whatsapp_allowed_number, text, urgent=True)

    def _notify_health_alert(text: str) -> None:
        _send_text(config.whatsapp_allowed_number, text)

    scheduler = ReminderScheduler(store, notify=_notify_reminder)
    health_monitor = HealthMonitor(store, notify=_notify_health_alert)

    @asynccontextmanager
    async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
        scheduler.start()
        health_monitor.start()
        yield
        scheduler.stop()
        health_monitor.stop()

    app = FastAPI(title="Orion WhatsApp webhook", lifespan=_lifespan)

    @app.get("/webhook")
    def verify_webhook(request: Request) -> Response:
        params = request.query_params
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge", "")
        if mode == "subscribe" and token == config.whatsapp_verify_token and config.whatsapp_verify_token:
            return Response(content=challenge, media_type="text/plain")
        return Response(status_code=403)

    @app.post("/webhook", response_model=None)
    async def receive_webhook(request: Request, background_tasks: BackgroundTasks) -> dict | Response:
        body = await request.body()
        if not _verify_webhook_signature(body, request.headers.get("x-hub-signature-256")):
            logger.warning("Rejected WhatsApp webhook POST with an invalid/missing signature.")
            return Response(status_code=403)

        payload = await request.json()
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    # Runs after this handler returns so Meta gets its 200
                    # OK immediately -- agent.respond() plus tool calls is
                    # easily several seconds, and Meta retries webhook
                    # deliveries that don't get a prompt response.
                    background_tasks.add_task(_process_message, agent, tts, message)
        return {"status": "ok"}

    return app


def main() -> None:
    configure_logging()
    if not config.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
    missing = [
        name
        for name, value in [
            ("WHATSAPP_ACCESS_TOKEN", config.whatsapp_access_token),
            ("WHATSAPP_PHONE_NUMBER_ID", config.whatsapp_phone_number_id),
            ("WHATSAPP_VERIFY_TOKEN", config.whatsapp_verify_token),
            ("WHATSAPP_APP_SECRET", config.whatsapp_app_secret),
            ("WHATSAPP_ALLOWED_NUMBER", config.whatsapp_allowed_number),
        ]
        if not value
    ]
    if missing:
        raise SystemExit(f"Missing required WhatsApp config: {', '.join(missing)}. See README §21.")

    purge_old_outputs(Path("outputs"), config.outputs_retention_days)

    memory = Memory()
    store = Store()
    agent = Agent(memory, build_registry(memory, store))

    tts = get_synthesizer_if_available()
    if tts is None:
        logger.info(
            "No TTS backend available (set ELEVENLABS_API_KEY, or place a Piper model in "
            "~/.local/share/piper/) — voice messages will get text replies only."
        )

    app = build_app(agent, store, tts)

    logger.info(
        "%s is listening for WhatsApp webhooks on port %d.", config.assistant_name, config.whatsapp_webhook_port
    )
    uvicorn.run(app, host="127.0.0.1", port=config.whatsapp_webhook_port)


if __name__ == "__main__":
    main()
