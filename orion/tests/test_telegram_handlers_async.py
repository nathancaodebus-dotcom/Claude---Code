"""interfaces/telegram_bot.py's handle_text/handle_voice run agent.respond()
(and, for voice, transcription/TTS) via asyncio.to_thread specifically so a
slow reply doesn't freeze the bot's single event loop — which would also
stall JobQueue-delivered reminders/health alerts and further incoming
messages for the same duration. These tests prove that concretely: an
independent async task scheduled alongside the handler must keep making
progress while the handler's blocking work is in flight, which is only
possible if that work actually runs off the event loop thread."""
from __future__ import annotations

import asyncio
import time

import pytest

from core import attachments
from core.config import config
from core.store import Store
from interfaces import telegram_bot


class _FakeUser:
    id = 42


class _FakeMessage:
    def __init__(self, text: str = ""):
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class _FakeUpdate:
    def __init__(self, text: str = ""):
        self.effective_user = _FakeUser()
        self.message = _FakeMessage(text)


class _SlowAgent:
    """respond() blocks synchronously for a while, standing in for a real
    multi-round-trip Claude call."""

    def respond(self, session_id: str, text: str) -> str:
        time.sleep(0.3)
        return "reply"


async def _run_ticker(iterations: int = 5, interval: float = 0.05) -> None:
    """Pure async work with no blocking calls of its own — if the event
    loop is free, this finishes in ~iterations*interval regardless of what
    else is running alongside it. gather() below runs it next to
    handle_text and checks the *total* wall-clock time: run concurrently
    (handle_text's blocking call correctly offloaded via asyncio.to_thread),
    the two overlap and the total is close to whichever is longer. Run
    sequentially (handle_text blocking the loop directly), this can't even
    start until handle_text's blocking call finishes, and the total is
    close to their *sum* instead — that's the difference this test checks
    for, not merely that this eventually completes."""
    for _ in range(iterations):
        await asyncio.sleep(interval)


@pytest.fixture
def app():
    # config is a frozen dataclass singleton read once at import time — build_application
    # reads config.telegram_bot_token internally, so it needs a real-looking value to
    # construct an Application at all (Application.builder().token(...).build() validates
    # the token is non-empty even though it never makes a network call at build time).
    # See tests/test_sql_tool.py / test_deploy_tool.py for the same object.__setattr__
    # pattern used to poke a frozen config field for a single test.
    original = config.telegram_bot_token
    object.__setattr__(config, "telegram_bot_token", "123456:ABC-fake-token-for-tests")
    try:
        yield telegram_bot.build_application(_SlowAgent(), Store(db_path=":memory:"), None)
    finally:
        object.__setattr__(config, "telegram_bot_token", original)


@pytest.mark.asyncio
async def test_handle_text_runs_agent_respond_off_the_event_loop(monkeypatch, app):
    monkeypatch.setattr(telegram_bot, "_is_authorized", lambda update: True)
    attachments.drain()  # ensure a clean slate regardless of what earlier tests left queued

    handle_text = app.handlers[0][0].callback
    update = _FakeUpdate("hello")

    start = time.monotonic()
    await asyncio.gather(handle_text(update, None), _run_ticker())
    elapsed = time.monotonic() - start

    # Concurrent: ~max(0.3, 0.25) = 0.3s. Sequential (blocking the loop):
    # ~0.3 + 0.25 = 0.55s. 0.45s cleanly separates the two.
    assert elapsed < 0.45, f"took {elapsed:.2f}s — looks like handle_text blocked the event loop"
    assert update.message.replies == ["reply"]


@pytest.mark.asyncio
async def test_handle_text_rejects_unauthorized_users_without_calling_agent(monkeypatch, app):
    monkeypatch.setattr(telegram_bot, "_is_authorized", lambda update: False)

    handle_text = app.handlers[0][0].callback
    update = _FakeUpdate("hello")

    await handle_text(update, None)

    assert update.message.replies == []
