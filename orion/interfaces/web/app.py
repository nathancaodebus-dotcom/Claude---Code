"""Local web interface — a HUD-styled browser UI for the same Orion every
other interface talks to (core/agent.py's Agent, shared Memory/Store/tool
registry). This is a different way to look at Orion, not a different
assistant: swap this for cli.py and everything (memory, tools, reminders)
behaves identically.

Single-user, single-session, matching cli.py's SESSION_ID convention — two
browser tabs open at once share the same conversation, same as running the
CLI twice would with the same ORION_DB_PATH.

Run with: python -m interfaces.web.app
"""
from __future__ import annotations

import base64
import io
import json
import queue
import tempfile
import threading
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Iterator

import uvicorn
from fastapi import FastAPI, File
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import attachments
from core.agent import Agent
from core.config import config
from core.health_monitor import HealthMonitor
from core.logging_setup import configure_logging
from core.memory import Memory
from core.outputs_cleanup import purge_old_outputs
from core.scheduler import ReminderScheduler
from core.stt import join_confident_segments
from core.store import Store
from core.tts import get_synthesizer_if_available
from tools.registry_builder import build_registry

SESSION_ID = "web"
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_OUTPUTS_DIR = Path("outputs")

_memory = Memory()
_store = Store()
_agent = Agent(_memory, build_registry(_memory, _store))

# Same TTS backends (ElevenLabs / Piper / Edge TTS) Telegram and the voice
# loop already use — see core/tts.py. None if none of the three is
# configured, in which case _synthesize_wav_b64 below degrades to the
# equalizer-only animation the HUD had before, exactly like a voice message
# with no TTS backend falls back to text-only on Telegram.
_tts = get_synthesizer_if_available()


def _synthesize_wav_b64(text: str) -> str | None:
    """Wraps core/tts.py's raw 16-bit PCM into a WAV container browsers can
    play natively (no ffmpeg/Opus transcoding needed here, unlike Telegram's
    voice-note requirement), base64-encoded so it can ride the existing SSE
    "sentence" event instead of needing a second endpoint or a websocket."""
    if _tts is None:
        return None
    pcm = _tts.synthesize(text)
    if not pcm:
        return None
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(_tts.sample_rate)
        wav_file.writeframes(pcm)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


# Same faster-whisper model the Pi voice loop and Telegram voice messages
# transcribe with, loaded once on first use rather than at import time —
# it takes a couple of seconds to load, not worth paying on every process
# start for a HUD session that might never touch the mic button. None if
# requirements-voice.txt isn't installed, same optional-dependency shape
# as _tts above.
_whisper_model = None
_whisper_model_lock = threading.Lock()


def _get_whisper_model():
    global _whisper_model
    with _whisper_model_lock:
        if _whisper_model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                return None
            _whisper_model = WhisperModel(config.whisper_model_size, device="cpu", compute_type="int8")
        return _whisper_model


# Reminders due and health alerts arrive on their own background threads
# (same notify-callback shape cli.py prints and voice_loop.py speaks) and
# get fanned out to every open browser tab as they happen, via one queue
# per connected /api/events stream.
_event_queues: list[queue.Queue] = []
_event_queues_lock = threading.Lock()


def _broadcast_event(text: str) -> None:
    payload = {"type": "notification", "text": text}
    with _event_queues_lock:
        queues = list(_event_queues)
    for q in queues:
        q.put(payload)


_scheduler = ReminderScheduler(_store, notify=_broadcast_event)
_health_monitor = HealthMonitor(_store, notify=_broadcast_event)

# FastAPI runs sync path operations (chat() below) in a thread pool, so two
# /api/chat requests for the same session — two open browser tabs, or a
# rapid double-send — can genuinely run concurrently. Both would call
# Agent.respond_streaming(SESSION_ID, ...) at once, racing its read-history/
# append-message sequence against each other: worst case, two consecutive
# "user" messages land in the same history with no assistant reply between
# them, which the Messages API's strict role-alternation rejects outright.
# One lock per session (there's only ever one, "web", today, but this keys
# by session_id rather than hardcoding that) rejects the second request
# cleanly instead of corrupting the shared conversation.
_chat_locks: dict[str, threading.Lock] = {}
_chat_locks_guard = threading.Lock()


def _chat_lock(session_id: str) -> threading.Lock:
    with _chat_locks_guard:
        return _chat_locks.setdefault(session_id, threading.Lock())


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    purge_old_outputs(_OUTPUTS_DIR, config.outputs_retention_days)
    _scheduler.start()
    _health_monitor.start()
    yield
    _scheduler.stop()
    _health_monitor.stop()


app = FastAPI(title="Orion", lifespan=_lifespan)


class ChatRequest(BaseModel):
    message: str


@app.get("/api/status")
def status() -> dict:
    return {
        "assistant_name": config.assistant_name,
        "model": config.model,
        "ready": bool(config.anthropic_api_key),
    }


def _stream_chat(message: str) -> Iterator[str]:
    """Runs Agent.respond_streaming (a blocking call with an on_sentence
    callback) on a background thread and relays each sentence to the
    browser as a Server-Sent Event as soon as it's ready — the same
    sentence-at-a-time responsiveness the voice interfaces get, just
    rendered as text appearing progressively instead of spoken aloud."""
    events: queue.Queue = queue.Queue()
    _DONE = object()

    lock = _chat_lock(SESSION_ID)
    if not lock.acquire(blocking=False):
        error = json.dumps(
            {"type": "error", "text": "Orion is still answering the previous message — wait for it to finish."}
        )
        yield f"data: {error}\n\n"
        return

    def on_sentence(text: str) -> None:
        events.put({"type": "sentence", "text": text, "audio": _synthesize_wav_b64(text)})

    def run() -> None:
        try:
            final_text = _agent.respond_streaming(SESSION_ID, message, on_sentence=on_sentence)
            events.put({"type": "done", "text": final_text, "attachments": attachments.drain()})
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI, never a crash
            events.put({"type": "error", "text": str(exc)})
        finally:
            lock.release()
            events.put(_DONE)

    threading.Thread(target=run, daemon=True).start()

    while True:
        item = events.get()
        if item is _DONE:
            return
        yield f"data: {json.dumps(item)}\n\n"


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    message = req.message.strip()
    if not message:
        error = json.dumps({"type": "error", "text": "Empty message."})
        return StreamingResponse(iter([f"data: {error}\n\n"]), media_type="text/event-stream")
    return StreamingResponse(_stream_chat(message), media_type="text/event-stream")


@app.post("/api/transcribe")
def transcribe(audio: bytes = File(...)) -> dict:
    """Push-to-talk mic input for the HUD: the browser records a clip (any
    container MediaRecorder produces — webm/opus in Chrome/Edge, ogg/opus
    in Firefox) and posts the raw bytes here. faster-whisper decodes
    whatever container it's given via PyAV, the same way telegram_bot.py
    feeds it Telegram's .ogg voice notes directly with no manual
    transcoding step — so this needs no ffmpeg conversion first, just a
    file on disk for WhisperModel.transcribe() to open (it doesn't accept
    raw bytes directly)."""
    model = _get_whisper_model()
    if model is None:
        return {
            "error": "Speech-to-text isn't available — install requirements-voice.txt (faster-whisper) first."
        }
    if not audio:
        return {"error": "No audio received."}

    # delete=False + close before transcribe, not the with-block-holds-it-
    # open shape used elsewhere: on Windows specifically (not Linux/Mac,
    # where a second open() on an already-open file is fine), a file still
    # held open by this process's own NamedTemporaryFile handle can't be
    # opened a second time by anything else -- confirmed live, faster-
    # whisper's own attempt to open tmp.name to decode it raised
    # PermissionError ("used by another process"), an uncaught 500 for
    # every single transcription attempt on Windows. Closing this
    # process's handle first before handing the path to faster-whisper
    # avoids the conflict; delete=False + the manual unlink in `finally`
    # replaces the auto-delete the with-block would otherwise have done.
    tmp = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
    try:
        tmp.write(audio)
        tmp.close()
        segments, _ = model.transcribe(tmp.name, language=config.voice_language)
        text = join_confident_segments(segments)
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    if not text:
        return {"error": "Didn't catch that — could you repeat?"}
    return {"text": text}


def _stream_events() -> Iterator[str]:
    q: queue.Queue = queue.Queue()
    with _event_queues_lock:
        _event_queues.append(q)
    try:
        while True:
            item = q.get()
            yield f"data: {json.dumps(item)}\n\n"
    finally:
        with _event_queues_lock:
            if q in _event_queues:
                _event_queues.remove(q)


@app.get("/api/events")
def events() -> StreamingResponse:
    return StreamingResponse(_stream_events(), media_type="text/event-stream")


_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
# Generated files (images, documents, QR codes, ...) land under outputs/ —
# mounted so the UI can show/download them directly by the relative path
# attachments.drain() already returns. Registered before the catch-all
# static mount below (Starlette matches routes in registration order; a
# "/" mount added first would swallow every path under it, this one included).
app.mount("/outputs", StaticFiles(directory=str(_OUTPUTS_DIR)), name="outputs")
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")


def main() -> None:
    configure_logging()
    if not config.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
    uvicorn.run(app, host="127.0.0.1", port=config.web_port)


if __name__ == "__main__":
    main()
