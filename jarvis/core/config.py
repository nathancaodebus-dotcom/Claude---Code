"""Central configuration, loaded from environment variables (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _get(key: str, default: str | None = None) -> str | None:
    value = os.getenv(key, default)
    return value if value != "" else default


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str | None = field(default_factory=lambda: _get("ANTHROPIC_API_KEY"))
    model: str = field(default_factory=lambda: _get("JARVIS_MODEL", "claude-sonnet-5"))
    assistant_name: str = field(default_factory=lambda: _get("JARVIS_NAME", "Jarvis"))
    db_path: str = field(default_factory=lambda: _get("JARVIS_DB_PATH", "./jarvis.db"))

    telegram_bot_token: str | None = field(default_factory=lambda: _get("TELEGRAM_BOT_TOKEN"))
    telegram_allowed_user_id: str | None = field(
        default_factory=lambda: _get("TELEGRAM_ALLOWED_USER_ID")
    )

    google_credentials_path: str = field(
        default_factory=lambda: _get("GOOGLE_CREDENTIALS_PATH", "./credentials.json")
    )
    google_token_path: str = field(
        default_factory=lambda: _get("GOOGLE_TOKEN_PATH", "./token.json")
    )

    home_assistant_url: str | None = field(default_factory=lambda: _get("HOME_ASSISTANT_URL"))
    home_assistant_token: str | None = field(
        default_factory=lambda: _get("HOME_ASSISTANT_TOKEN")
    )

    wake_word: str = field(default_factory=lambda: _get("WAKE_WORD", "hey_jarvis"))
    voice_language: str = field(default_factory=lambda: _get("VOICE_LANGUAGE", "fr"))


config = Config()
