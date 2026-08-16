"""interfaces/telegram_bot.py's check_reminders JobQueue callback.
Regression test for a real bug found during a full-codebase audit:
handle_voice already offloads its TTS+ffmpeg call via asyncio.to_thread
(see tests/test_telegram_handlers_async.py's docstring for why that
matters -- it's not just about this one job, a blocked event loop also
stalls every other update and this same polling loop), but check_reminders
called the identical function directly, synchronously, blocking the bot's
single event loop for the full synth+encode duration of every reminder
with TTS configured."""
from __future__ import annotations

import asyncio
import time

import pytest

from core.config import config
from core.store import Store
from interfaces import telegram_bot


class _FakeMessage:
    id = 1


class _FakeBot:
    def __init__(self):
        self.sent_messages: list[str] = []
        self.sent_voices: list[bytes] = []

    async def send_message(self, chat_id, text):
        self.sent_messages.append(text)
        return _FakeMessage()

    async def send_voice(self, chat_id, voice):
        self.sent_voices.append(voice)
        return _FakeMessage()


class _FakeContext:
    def __init__(self, bot):
        self.bot = bot


class _SlowSynthesizer:
    """A TTS backend whose sample rate/etc. don't matter here -- only
    used as a non-None sentinel so build_application wires up the TTS
    branch of check_reminders at all."""

    sample_rate = 22050


def _slow_synthesize_to_ogg_opus(synthesizer, text, urgent=False):
    time.sleep(0.3)
    return b"fake-ogg-bytes"


async def _run_ticker(iterations: int = 5, interval: float = 0.05) -> None:
    for _ in range(iterations):
        await asyncio.sleep(interval)


@pytest.fixture
def store_with_due_reminder():
    store = Store(db_path=":memory:")
    store.add_reminder("test reminder", due_at=0.0)  # already due
    return store


@pytest.fixture
def app(store_with_due_reminder):
    original_token = config.telegram_bot_token
    original_user = config.telegram_allowed_user_id
    object.__setattr__(config, "telegram_bot_token", "123456:ABC-fake-token-for-tests")
    object.__setattr__(config, "telegram_allowed_user_id", "42")
    try:

        class _NoopAgent:
            def respond(self, session_id, text):
                return "unused"

        yield telegram_bot.build_application(_NoopAgent(), store_with_due_reminder, _SlowSynthesizer())
    finally:
        object.__setattr__(config, "telegram_bot_token", original_token)
        object.__setattr__(config, "telegram_allowed_user_id", original_user)


def _find_job_callback(app, index: int):
    jobs = app.job_queue.jobs()
    return jobs[index].callback


@pytest.mark.asyncio
async def test_check_reminders_does_not_block_the_event_loop(monkeypatch, app):
    monkeypatch.setattr(telegram_bot, "_synthesize_to_ogg_opus", _slow_synthesize_to_ogg_opus)
    check_reminders = _find_job_callback(app, 0)
    bot = _FakeBot()
    context = _FakeContext(bot)

    start = time.monotonic()
    await asyncio.gather(check_reminders(context), _run_ticker())
    elapsed = time.monotonic() - start

    # Same timing argument as test_telegram_handlers_async.py: concurrent
    # is ~max(0.3, 0.25) = 0.3s; blocking the loop is ~0.3 + 0.25 = 0.55s.
    assert elapsed < 0.45, f"took {elapsed:.2f}s — looks like check_reminders blocked the event loop"
    assert bot.sent_messages == ["⏰ Reminder: test reminder"]
    assert bot.sent_voices == [b"fake-ogg-bytes"]
