"""Terminal chat interface — useful for local testing before wiring up
Telegram or the voice loop, and works identically on the Pi or a laptop."""
from __future__ import annotations

from core import attachments
from core.agent import Agent
from core.config import config
from core.health_monitor import HealthMonitor
from core.logging_setup import configure_logging
from core.memory import Memory
from core.scheduler import ReminderScheduler
from core.store import Store
from tools.registry_builder import build_registry

SESSION_ID = "cli"


def main() -> None:
    configure_logging()
    if not config.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")

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

        reply = agent.respond(SESSION_ID, user_input)
        print(f"{config.assistant_name}> {reply}\n")

        for path in attachments.drain():
            print(f"[attachment saved: {path}]")

    scheduler.stop()
    health_monitor.stop()


if __name__ == "__main__":
    main()
