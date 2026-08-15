"""Central configuration, loaded from environment variables (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _get(key: str, default: str | None = None) -> str | None:
    value = os.getenv(key, default)
    return value if value != "" else default


# Per-language default Edge TTS voices, keyed by the same short code
# VOICE_LANGUAGE already uses for Piper model matching. Only the languages
# this project's other defaults (VOICE_LANGUAGE="fr") and README examples
# actually cover; anything else needs EDGE_TTS_VOICE set explicitly (see
# https://github.com/rany2/edge-tts for the full voice list, `edge-tts
# --list-voices`).
_EDGE_TTS_DEFAULT_VOICES = {
    "fr": "fr-FR-HenriNeural",
    "en": "en-US-GuyNeural",
}


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
    # On by default: routes each user message to fast_model (Haiku) or
    # model (Sonnet) by heuristic complexity (core/routing.py) instead of
    # always paying Sonnet's latency/cost for questions that don't need
    # it — "what time is it" doesn't need the same model as "compare these
    # two approaches and explain the tradeoffs." Cloud-only (both tiers are
    # still Claude) — not a switch to a local/offline model, see README §19.
    model_routing_enabled: bool = field(
        default_factory=lambda: _get("ORION_MODEL_ROUTING_ENABLED", "true").lower() == "true"
    )
    assistant_name: str = field(default_factory=lambda: _get("ORION_NAME", "Orion"))
    db_path: str = field(default_factory=lambda: _get("ORION_DB_PATH", "./orion.db"))
    # core/logging_setup.py: a rotating file log alongside console output, so
    # a headless/backgrounded run (systemd, a Task Scheduler job, ...) leaves
    # a trail to diagnose after the fact instead of only whatever was left in
    # a terminal that's since closed.
    log_path: str = field(default_factory=lambda: _get("ORION_LOG_PATH", "./orion.log"))
    # core/outputs_cleanup.py: every generated file (images, documents,
    # videos, ...) lands under outputs/ and nothing ever removed an old one
    # — 0 (default) means disabled, since auto-deleting a user's generated
    # files without being asked isn't something this project does unprompted.
    # Set to a day count to opt in to an automatic sweep at each interface's
    # startup; the clean_old_outputs tool works either way, with an explicit
    # days argument overriding this default for a one-off manual cleanup.
    outputs_retention_days: int = field(
        default_factory=lambda: int(_get("ORION_OUTPUTS_RETENTION_DAYS", "0"))
    )
    # interfaces/web/app.py — local HUD-styled browser UI.
    web_port: int = field(default_factory=lambda: int(_get("ORION_WEB_PORT", "8420")))

    telegram_bot_token: str | None = field(default_factory=lambda: _get("TELEGRAM_BOT_TOKEN"))
    telegram_allowed_user_id: str | None = field(
        default_factory=lambda: _get("TELEGRAM_ALLOWED_USER_ID")
    )

    # interfaces/whatsapp_bot.py — WhatsApp Cloud API (Meta's official
    # Business API), webhook-based rather than polling like python-telegram-
    # bot above. See README §21 for the full setup (Meta app, phone number,
    # webhook URL).
    whatsapp_access_token: str | None = field(default_factory=lambda: _get("WHATSAPP_ACCESS_TOKEN"))
    whatsapp_phone_number_id: str | None = field(
        default_factory=lambda: _get("WHATSAPP_PHONE_NUMBER_ID")
    )
    # Arbitrary string you choose yourself when configuring the webhook in
    # the Meta dashboard -- proves the GET verification request is the one
    # you set up, not a guess by someone else who found the URL.
    whatsapp_verify_token: str | None = field(default_factory=lambda: _get("WHATSAPP_VERIFY_TOKEN"))
    # Meta App Secret, used to verify the X-Hub-Signature-256 header on every
    # inbound webhook POST -- without this, anyone who finds the webhook URL
    # could POST a fake message claiming to be from whatsapp_allowed_number
    # and have Orion treat it as the owner. Not optional the way the other
    # WhatsApp settings are; see interfaces/whatsapp_bot.py.
    whatsapp_app_secret: str | None = field(default_factory=lambda: _get("WHATSAPP_APP_SECRET"))
    # E.164 phone number without the leading '+' (matches the "wa_id" format
    # WhatsApp's webhook payloads use), e.g. "41791234567".
    whatsapp_allowed_number: str | None = field(default_factory=lambda: _get("WHATSAPP_ALLOWED_NUMBER"))
    whatsapp_api_version: str = field(default_factory=lambda: _get("WHATSAPP_API_VERSION", "v21.0"))
    whatsapp_webhook_port: int = field(
        default_factory=lambda: int(_get("WHATSAPP_WEBHOOK_PORT", "8422"))
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
    # Off by default: barge-in (saying the wake word again to interrupt
    # Orion mid-reply) listens with the same wake-word model used for
    # normal wake detection, which is far less prone to false-triggering
    # on Orion's own synthesized voice than the plain RMS/volume check this
    # used to be — that version reliably heard *itself* on a laptop's
    # built-in speakers+mic (inches apart, no real acoustic echo
    # cancellation) and cut its own replies off for no reason (see README
    # §7). Still not a hard guarantee against self-triggering without real
    # AEC or headphones, so it stays an explicit opt-in rather than a
    # default.
    voice_barge_in_enabled: bool = field(
        default_factory=lambda: _get("VOICE_BARGE_IN_ENABLED", "false").lower() == "true"
    )

    # Offline fallback (core/offline_agent.py): a local Ollama server Orion
    # switches to automatically if a Claude call fails for a genuinely
    # offline-shaped reason (no network, Anthropic outage, empty account
    # balance) — never on its own initiative otherwise. Requires Ollama
    # installed separately (ollama.com) with OLLAMA_MODEL already pulled
    # (`ollama pull llama3.1:8b`); if Ollama isn't reachable at the
    # configured host, Orion just behaves as it does today — no crash, no
    # fallback, same as any other optional integration here. See README §7.
    ollama_host: str = field(default_factory=lambda: _get("OLLAMA_HOST", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: _get("OLLAMA_MODEL", "llama3.1:8b"))

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

    # Path to a Claude-Desktop-style {"mcpServers": {...}} JSON file
    # (core/mcp_client.py) -- lets Orion connect to external MCP servers
    # and use their tools alongside the hand-written registry. Off unless
    # set, see README §20 and mcp_servers.example.json.
    mcp_servers_config_path: str | None = field(default_factory=lambda: _get("MCP_SERVERS_CONFIG_PATH"))

    # core/browser_session.py / tools/browser_tools.py -- Playwright-backed
    # browser automation. Comma-separated hostnames; when set, browser_navigate
    # refuses any URL outside this list. Off (unrestricted) by default,
    # matching tools/web_tools.py's existing unrestricted fetch_webpage. See
    # README §22.
    browser_allowed_domains: str | None = field(default_factory=lambda: _get("BROWSER_ALLOWED_DOMAINS"))
    # Points at a system-installed Chromium instead of downloading
    # Playwright's own bundled copy -- useful on a Raspberry Pi or other
    # low-resource device. None (default) uses Playwright's normal browser
    # resolution.
    browser_chromium_executable_path: str | None = field(
        default_factory=lambda: _get("BROWSER_CHROMIUM_EXECUTABLE_PATH")
    )

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

    # Edge TTS (core/tts.py's EdgeTTSSynthesizer) — the free, no-API-key,
    # no-local-model cloud fallback used when neither ELEVENLABS_API_KEY nor
    # a local Piper voice model is available. Defaults from VOICE_LANGUAGE so
    # it works out of the box for fr/en without any extra .env entry; set
    # EDGE_TTS_VOICE directly to override the voice or support another
    # language.
    edge_tts_voice: str = field(
        default_factory=lambda: _get("EDGE_TTS_VOICE")
        or _EDGE_TTS_DEFAULT_VOICES.get(_get("VOICE_LANGUAGE", "fr"), "en-US-GuyNeural")
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
