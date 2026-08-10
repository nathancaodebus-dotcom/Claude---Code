"""Terminal chat interface — useful for local testing before wiring up
Telegram or the voice loop, and works identically on the Pi or a laptop."""
from __future__ import annotations

from core.agent import Agent
from core.config import config
from core.memory import Memory
from tools.registry_builder import build_registry

SESSION_ID = "cli"


def main() -> None:
    if not config.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")

    memory = Memory()
    agent = Agent(memory, build_registry(memory))

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


if __name__ == "__main__":
    main()
