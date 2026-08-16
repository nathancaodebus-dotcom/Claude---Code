"""Telegram interface — this is the fastest path to 'works on my Android phone':
no native app to build, push notifications for free, and voice messages work
out of the box. Restricted to a single owner user id so the assistant stays
private even though Telegram bots are technically public endpoints.

Voice messages get a spoken reply back, not just text, using the same TTS
backend as the Raspberry Pi voice loop (core/tts.py) — ElevenLabs if
configured, otherwise a local Piper model if one happens to be present on
whatever machine runs this bot. If neither is available, replies stay
text-only exactly as before; nothing breaks.

Also the interface that delivers proactive pushes: a JobQueue job polls the
reminder store and messages the owner when one comes due, and a second job
polls for tools that have started failing repeatedly (core/health_monitor.py)
so a dead integration surfaces on its own instead of waiting to be asked.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
import threading
from pathlib import Path

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from core import attachments
from core.agent import Agent
from core.config import config
from core.health_monitor import pending_alerts
from core.logging_setup import configure_logging
from core.memory import Memory
from core.outputs_cleanup import purge_old_outputs
from core.stt import join_confident_segments
from core.store import Store
from core.tts import Synthesizer, get_synthesizer_if_available
from core.tts import synthesize_to_ogg_opus as _synthesize_to_ogg_opus
from tools.registry_builder import build_registry

logger = logging.getLogger("orion.telegram")

SESSION_ID = "telegram"
REMINDER_POLL_INTERVAL_S = 15
HEALTH_POLL_INTERVAL_S = 300


def _is_authorized(update: Update) -> bool:
    if not config.telegram_allowed_user_id:
        logger.warning("TELEGRAM_ALLOWED_USER_ID is not set — refusing all messages for safety.")
        return False
    return str(update.effective_user.id) == str(config.telegram_allowed_user_id)


_whisper_model = None
_whisper_model_lock = threading.Lock()


def _get_whisper_model():
    """Lazily-loaded, cached singleton -- same pattern interfaces/web/app.py
    and interfaces/whatsapp_bot.py already use. This used to construct a
    fresh WhisperModel on every single voice message (a couple of seconds
    of disk I/O + weight init paid again and again), found during a
    full-codebase audit; those two sibling interfaces had already fixed it,
    this one just hadn't gone through the same pass yet."""
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
    """Best-effort local transcription of voice messages using faster-whisper,
    if the optional voice dependencies (requirements-voice.txt) are installed."""
    model = _get_whisper_model()
    if model is None:
        return None
    segments, _ = model.transcribe(str(audio_path), language=config.voice_language)
    return join_confident_segments(segments)


async def _send_attachments(update: Update) -> None:
    for path in attachments.drain():
        if path.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
            await update.message.reply_photo(photo=path)
        else:
            await update.message.reply_document(document=path)


def build_application(agent: Agent, store: Store, tts: Synthesizer | None) -> Application:
    application = Application.builder().token(config.telegram_bot_token).build()

    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _is_authorized(update):
            return
        # agent.respond() is a blocking call — often several Claude round
        # trips plus tool calls, easily seconds long. Calling it directly
        # here would freeze this bot's single asyncio event loop for that
        # whole duration: no other update gets processed, and the JobQueue
        # (reminders, health alerts, both scheduled on the same loop) stalls
        # right along with it. asyncio.to_thread runs it on a worker thread
        # instead, so the loop stays free to keep polling and firing jobs
        # while a reply is being generated.
        reply = await asyncio.to_thread(agent.respond, SESSION_ID, update.message.text)
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
            # CPU-bound (loads/runs a local Whisper model) — same event-loop-
            # freezing concern as agent.respond() above.
            transcript = await asyncio.to_thread(_transcribe, audio_path)

        if transcript is None:
            # _transcribe returns None specifically for "faster-whisper isn't
            # installed" (ImportError) — distinct from "" below, which means
            # it ran fine but didn't hear anything it was confident was real
            # speech (near-silence, background noise). Conflating the two
            # used to tell someone with working STT to go install a package
            # they already have, right after Whisper's own hallucination
            # filter (core/stt.py) correctly caught a bad recording.
            await update.message.reply_text(
                "I can't transcribe voice messages yet — install requirements-voice.txt "
                "(faster-whisper) to enable it, or send text for now."
            )
            return
        if not transcript:
            await update.message.reply_text("Didn't catch that — could you send it again?")
            return

        reply = await asyncio.to_thread(agent.respond, SESSION_ID, transcript)
        await update.message.reply_text(f"\U0001f3a4 “{transcript}”\n\n{reply}")

        if tts is not None:
            # Also blocking: TTS synthesis plus an ffmpeg subprocess call.
            ogg_bytes = await asyncio.to_thread(_synthesize_to_ogg_opus, tts, reply)
            if ogg_bytes:
                await update.message.reply_voice(voice=ogg_bytes)

        await _send_attachments(update)

    async def check_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
        for reminder in store.due_reminders():
            await context.bot.send_message(
                chat_id=config.telegram_allowed_user_id, text=f"⏰ Reminder: {reminder.text}"
            )
            if tts is not None:
                # Blocking (TTS network call + an ffmpeg subprocess) --
                # handle_voice already offloads the identical call via
                # asyncio.to_thread a few lines up; this one didn't, so
                # every reminder with TTS configured froze the bot's single
                # event loop (no other update processed, and this same
                # JobQueue polling loop stalls) for the full synth+encode
                # duration. Found during a full-codebase audit.
                ogg_bytes = await asyncio.to_thread(_synthesize_to_ogg_opus, tts, reminder.text, urgent=True)
                if ogg_bytes:
                    await context.bot.send_voice(chat_id=config.telegram_allowed_user_id, voice=ogg_bytes)
            store.mark_reminder_delivered(reminder.id)

    async def check_health_alerts(context: ContextTypes.DEFAULT_TYPE) -> None:
        for tool_name, message in pending_alerts(store):
            await context.bot.send_message(chat_id=config.telegram_allowed_user_id, text=message)
            store.mark_health_alerted(tool_name)

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    if application.job_queue is not None:
        application.job_queue.run_repeating(check_reminders, interval=REMINDER_POLL_INTERVAL_S, first=5)
        application.job_queue.run_repeating(check_health_alerts, interval=HEALTH_POLL_INTERVAL_S, first=30)
    else:
        logger.warning(
            "JobQueue unavailable (install 'python-telegram-bot[job-queue]') — "
            "reminders and health alerts won't be pushed proactively, only listable via "
            "list_reminders / list_failed_commands."
        )
    return application


def main() -> None:
    configure_logging()
    if not config.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
    if not config.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. Create a bot via @BotFather first.")
    if not config.telegram_allowed_user_id:
        raise SystemExit(
            "TELEGRAM_ALLOWED_USER_ID is not set. Message @userinfobot to get your id."
        )

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

    application = build_application(agent, store, tts)

    logger.info("%s is listening on Telegram.", config.assistant_name)
    application.run_polling()


if __name__ == "__main__":
    main()
