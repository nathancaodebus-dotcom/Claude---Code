"""Terminal chat interface — useful for local testing before wiring up
Telegram or the voice loop, and works identically on the Pi or a laptop."""
from __future__ import annotations

import logging
from pathlib import Path

from core import attachments
from core.agent import Agent
from core.config import config
from core.health_monitor import HealthMonitor
from core.logging_setup import configure_logging
from core.memory import Memory
from core.outputs_cleanup import purge_old_outputs
from core.scheduler import ReminderScheduler
from core.store import Store
from tools.registry_builder import build_registry

logger = logging.getLogger("orion.cli")

SESSION_ID = "cli"


def main() -> None:
    configure_logging()
    if not config.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")

    # No-op unless ORION_OUTPUTS_RETENTION_DAYS is set — see
    # core/outputs_cleanup.py for why this is opt-in.
    purge_old_outputs(Path("outputs"), config.outputs_retention_days)

    memory = Memory()
    store = Store()
    agent = Agent(memory, build_registry(memory, store))

    scheduler = ReminderScheduler(store, notify=lambda text: print(f"\n{config.assistant_name}> {text}\n"))
    scheduler.start()

    health_monitor = HealthMonitor(store, notify=lambda text: print(f"\n{config.assistant_name}> {text}\n"))
    health_monitor.start()

    print(f"{config.assistant_name} is online. Type 'exit' to quit.\n")
    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break

        try:
            reply = agent.respond(SESSION_ID, user_input)
        except Exception:
            # Every other interface (voice_loop.py's run() loop, web/app.py's
            # _stream_chat) already catches around this same call and keeps
            # going -- an uncaught exception here (a SQLite hiccup, a
            # malformed tool schema, anything unexpected) used to take the
            # whole CLI process down and lose the session instead of just
            # failing the one turn.
            logger.exception("Turn failed.")
            print(f"{config.assistant_name}> Something went wrong on my end — try again?\n")
            continue
        print(f"{config.assistant_name}> {reply}\n")

        for path in attachments.drain():
            print(f"[attachment saved: {path}]")

    scheduler.stop()
    health_monitor.stop()


if __name__ == "__main__":
    main()
