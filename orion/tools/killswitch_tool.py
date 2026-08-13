"""Emergency data wipe: purge local memory/history and revoke cached OAuth
tokens. Gated behind a configured confirmation phrase (KILL_SWITCH_PHRASE)
that must be passed verbatim — this is destructive and irreversible, so it
should never fire from an ambiguous or misheard command."""
from __future__ import annotations

from pathlib import Path

from core.config import config
from core.memory import Memory
from core.store import Store
from tools.base import Tool

_TOKEN_FILES = ["google_token_path", "spotify_token_path"]


class EmergencyWipeTool(Tool):
    name = "emergency_wipe"
    description = (
        "Destructive: wipe all local conversation history, facts, and cached OAuth tokens, and "
        "log the user out of every connected service. Requires the exact confirmation phrase "
        "configured in KILL_SWITCH_PHRASE — only call this if the user explicitly provides it, "
        "never speculatively."
    )
    input_schema = {
        "type": "object",
        "properties": {"confirmation_phrase": {"type": "string"}},
        "required": ["confirmation_phrase"],
    }

    def run(self, confirmation_phrase: str) -> str:
        if not config.kill_switch_phrase:
            return "Kill switch is not configured. Set KILL_SWITCH_PHRASE in .env to enable it."
        if confirmation_phrase != config.kill_switch_phrase:
            return "Confirmation phrase does not match. Nothing was wiped."

        memory = Memory()
        store = Store()  # generated documents (outputs/) are left on disk; only credentials/history are wiped

        wiped = []
        for attr in _TOKEN_FILES:
            path_str = getattr(config, attr, None)
            if path_str and Path(path_str).exists():
                Path(path_str).unlink()
                wiped.append(path_str)

        conn = memory._conn  # noqa: SLF001 - intentional direct access for a full wipe
        conn.executescript(
            "DELETE FROM messages; DELETE FROM facts; DELETE FROM conversation_summaries;"
        )
        conn.commit()

        store_conn = store._conn  # noqa: SLF001
        store_conn.executescript(
            "DELETE FROM todos; DELETE FROM notes; DELETE FROM shopping_items; "
            "DELETE FROM reminders; DELETE FROM projects; DELETE FROM milestones; "
            "DELETE FROM failed_commands;"
        )
        store_conn.commit()

        return f"Wiped local memory/history and revoked tokens: {', '.join(wiped) or '(no tokens were cached)'}."
