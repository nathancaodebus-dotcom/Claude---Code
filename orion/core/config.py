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
    # Used for internal housekeeping calls that don't need frontier-level
    # reasoning (currently just conversation-summary consolidation) — a
    # faster/cheaper model there costs nothing in answer quality since the
    # user never sees its output directly, only the digest it produces.
    fast_model: str = field(
        default_factory=lambda: _get("ORION_FAST_MODEL", "claude-haiku-4-5-20251001")
    )
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

    # openWakeWord has no pretrained "hey_orion" model of its own, but a custom
    # one trained with scripts/wake_word_training/ (see that directory's
    # README for how and why) ships at wake_word_models/hey_orion.onnx —
    # interfaces/voice/voice_loop.py resolves this default to that file
    # automatically. Set WAKE_WORD to an openWakeWord bundled name (e.g.
    # hey_jarvis) or a path to your own model to use something else; a clear,
    # actionable error is raised at startup if nothing matches. See README §7.
    wake_word: str = field(default_factory=lambda: _get("WAKE_WORD", "hey_orion"))
    voice_language: str = field(default_factory=lambda: _get("VOICE_LANGUAGE", "fr"))
    # faster-whisper model size — trades accuracy for latency on CPU-only
    # machines (no CUDA config here; faster-whisper picks GPU automatically
    # via ctranslate2 if a working CUDA/cuDNN setup is present, otherwise
    # falls back to CPU). "small" is the most accurate that's still
    # reasonably fast on a laptop CPU; try "base" or "tiny" if replies feel
    # sluggish — each step down cuts transcription time roughly in half at
    # some cost to recognizing less common words/names. See README §7.
    whisper_model_size: str = field(default_factory=lambda: _get("WHISPER_MODEL_SIZE", "small"))

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

    # Image generation (Google Imagen via the Gemini API) — separate,
    # usage-billed API key, distinct from ANTHROPIC_API_KEY. No free tier;
    # each image costs real money (a few cents), which is why this tool
    # only registers when a key is actually present (see registry_builder.py)
    # rather than silently failing at call time.
    gemini_api_key: str | None = field(default_factory=lambda: _get("GEMINI_API_KEY"))
    gemini_image_model: str = field(
        default_factory=lambda: _get("GEMINI_IMAGE_MODEL", "imagen-4.0-generate-001")
    )

    # Website hosting (§13 level 2). Free/default path: push outputs/websites/<site>
    # to a GitHub repo and enable Pages — needs a token with repo scope.
    # Paid alternative: Infomaniak Web Hosting over SFTP.
    github_pages_token: str | None = field(default_factory=lambda: _get("GITHUB_PAGES_TOKEN"))
    github_pages_owner: str | None = field(default_factory=lambda: _get("GITHUB_PAGES_OWNER"))
    infomaniak_ftp_host: str | None = field(default_factory=lambda: _get("INFOMANIAK_FTP_HOST"))
    infomaniak_ftp_username: str | None = field(default_factory=lambda: _get("INFOMANIAK_FTP_USERNAME"))
    infomaniak_ftp_password: str | None = field(default_factory=lambda: _get("INFOMANIAK_FTP_PASSWORD"))

    # Microsoft 365 (Outlook Mail/Calendar/Contacts), alongside the existing
    # Google integration rather than replacing it — see tools/microsoft_auth.py.
    # MICROSOFT_CLIENT_ID is an Azure AD app registration's Application
    # (client) ID, registered as a public client (no client secret needed —
    # device code flow doesn't use one).
    microsoft_client_id: str | None = field(default_factory=lambda: _get("MICROSOFT_CLIENT_ID"))
    microsoft_token_path: str = field(
        default_factory=lambda: _get("MICROSOFT_TOKEN_PATH", "./microsoft_token.json")
    )

    # Shopify (e-commerce store management) — a custom app's Admin API
    # access token, not OAuth, since this manages the user's own store
    # rather than acting as a public app for other merchants.
    shopify_store_domain: str | None = field(default_factory=lambda: _get("SHOPIFY_STORE_DOMAIN"))
    shopify_access_token: str | None = field(default_factory=lambda: _get("SHOPIFY_ACCESS_TOKEN"))
    shopify_api_version: str = field(default_factory=lambda: _get("SHOPIFY_API_VERSION", "2024-10"))


config = Config()
