"""Telegram interface — this is the fastest path to 'works on my Android phone':
no native app to build, push notifications for free, and voice messages work
out of the box. Restricted to a single owner user id so the assistant stays
private even though Telegram bots are technically public endpoints.

Also the interface that delivers proactive reminders/timers: a JobQueue job
polls the reminder store and messages the owner when one comes due.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from core import attachments
from core.agent import Agent
from core.config import config
from core.memory import Memory
from core.store import Store
from tools.registry_builder import build_registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jarvis.telegram")

SESSION_ID = "telegram"
REMINDER_POLL_INTERVAL_S = 15


def _is_authorized(update: Update) -> bool:
    if not config.telegram_allowed_user_id:
        logger.warning("TELEGRAM_ALLOWED_USER_ID is not set — refusing all messages for safety.")
        return False
    return str(update.effective_user.id) == str(config.telegram_allowed_user_id)


def _transcribe(audio_path: Path) -> str | None:
    """Best-effort local transcription of voice messages using faster-whisper,
    if the optional voice dependencies (requirements-voice.txt) are installed."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None

    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio_path), language=config.voice_language)
    return " ".join(segment.text for segment in segments).strip()


async def _send_attachments(update: Update) -> None:
    for path in attachments.drain():
        if path.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
            await update.message.reply_photo(photo=path)
        else:
            await update.message.reply_document(document=path)


def build_application(agent: Agent, store: Store) -> Application:
    application = Application.builder().token(config.telegram_bot_token).build()

    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _is_authorized(update):
            return
        reply = agent.respond(SESSION_ID, update.message.text)
        await update.message.reply_text(reply)
        await _send_attachments(update)

    async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _is_authorized(update):
            return

        voice = update.message.voice or update.message.audio
        telegram_file = await context.bot.get_file(voice.file_id)

        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "voice.ogg"
            await telegram_file.download_to_drive(str(audio_path))
            transcript = _transcribe(audio_path)

        if not transcript:
            await update.message.reply_text(
                "I can't transcribe voice messages yet — install requirements-voice.txt "
                "(faster-whisper) to enable it, or send text for now."
            )
            return

        reply = agent.respond(SESSION_ID, transcript)
        await update.message.reply_text(f"\U0001f3a4 “{transcript}”\n\n{reply}")
        await _send_attachments(update)

    async def check_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
        for reminder in store.due_reminders():
            await context.bot.send_message(
                chat_id=config.telegram_allowed_user_id, text=f"⏰ Reminder: {reminder.text}"
            )
            store.mark_reminder_delivered(reminder.id)

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    if application.job_queue is not None:
        application.job_queue.run_repeating(check_reminders, interval=REMINDER_POLL_INTERVAL_S, first=5)
    else:
        logger.warning(
            "JobQueue unavailable (install 'python-telegram-bot[job-queue]') — "
            "reminders won't be pushed proactively, only listable via list_reminders."
        )
    return application


def main() -> None:
    if not config.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
    if not config.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. Create a bot via @BotFather first.")
    if not config.telegram_allowed_user_id:
        raise SystemExit(
            "TELEGRAM_ALLOWED_USER_ID is not set. Message @userinfobot to get your id."
        )

    memory = Memory()
    store = Store()
    agent = Agent(memory, build_registry(memory, store))
    application = build_application(agent, store)

    logger.info("%s is listening on Telegram.", config.assistant_name)
    application.run_polling()


if __name__ == "__main__":
    main()
