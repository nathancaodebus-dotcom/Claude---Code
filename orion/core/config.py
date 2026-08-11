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
    model: str = field(default_factory=lambda: _get("ORION_MODEL", "claude-sonnet-5"))
    assistant_name: str = field(default_factory=lambda: _get("ORION_NAME", "Orion"))
    db_path: str = field(default_factory=lambda: _get("ORION_DB_PATH", "./orion.db"))

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

    # openWakeWord has no pretrained "hey_orion" model — this only works once
    # you've trained a custom one (or switched wake-word engines) and pointed
    # WAKE_WORD at it; see README §7. interfaces/voice/voice_loop.py raises a
    # clear, actionable error at startup rather than a cryptic one if no
    # model matching this value can be loaded.
    wake_word: str = field(default_factory=lambda: _get("WAKE_WORD", "hey_orion"))
    voice_language: str = field(default_factory=lambda: _get("VOICE_LANGUAGE", "fr"))

    spotify_client_id: str | None = field(default_factory=lambda: _get("SPOTIFY_CLIENT_ID"))
    spotify_client_secret: str | None = field(default_factory=lambda: _get("SPOTIFY_CLIENT_SECRET"))
    spotify_redirect_uri: str = field(
        default_factory=lambda: _get("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
    )
    spotify_token_path: str = field(
        default_factory=lambda: _get("SPOTIFY_TOKEN_PATH", "./spotify_token.json")
    )

    youtube_api_key: str | None = field(default_factory=lambda: _get("YOUTUBE_API_KEY"))
    chromecast_name: str | None = field(default_factory=lambda: _get("CHROMECAST_NAME"))

    home_city: str | None = field(default_factory=lambda: _get("HOME_CITY"))

    caldav_url: str | None = field(default_factory=lambda: _get("CALDAV_URL"))
    caldav_username: str | None = field(default_factory=lambda: _get("CALDAV_USERNAME"))
    caldav_password: str | None = field(default_factory=lambda: _get("CALDAV_PASSWORD"))

    todoist_api_token: str | None = field(default_factory=lambda: _get("TODOIST_API_TOKEN"))

    obsidian_vault_path: str | None = field(default_factory=lambda: _get("OBSIDIAN_VAULT_PATH"))

    github_token: str | None = field(default_factory=lambda: _get("GITHUB_WATCH_TOKEN"))

    tmdb_api_key: str | None = field(default_factory=lambda: _get("TMDB_API_KEY"))

    backup_source_path: str | None = field(default_factory=lambda: _get("BACKUP_SOURCE_PATH"))
    backup_dest_path: str | None = field(default_factory=lambda: _get("BACKUP_DEST_PATH"))

    emergency_contact_chat_ids: str | None = field(
        default_factory=lambda: _get("EMERGENCY_CONTACT_CHAT_IDS")
    )

    sandbox_enabled: bool = field(
        default_factory=lambda: _get("SANDBOX_ENABLED", "false").lower() == "true"
    )

    sql_connection_string: str | None = field(default_factory=lambda: _get("SQL_CONNECTION_STRING"))

    deploy_commands: str | None = field(default_factory=lambda: _get("DEPLOY_COMMANDS"))

    elevenlabs_api_key: str | None = field(default_factory=lambda: _get("ELEVENLABS_API_KEY"))
    elevenlabs_voice_id: str = field(
        default_factory=lambda: _get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    )

    kill_switch_phrase: str | None = field(default_factory=lambda: _get("KILL_SWITCH_PHRASE"))

    hibp_api_key: str | None = field(default_factory=lambda: _get("HIBP_API_KEY"))


config = Config()
