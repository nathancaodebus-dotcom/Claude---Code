"""Send an urgent alert to pre-configured emergency contacts via Telegram —
uses the Bot API directly over HTTP so it works regardless of which
interface is running (doesn't need the Telegram interface to be the one
currently active)."""
from __future__ import annotations

import httpx

from core.config import config
from core.http import client
from tools.base import Tool


class EmergencyAlertTool(Tool):
    name = "send_emergency_alert"
    description = (
        "Send an urgent alert message to the user's pre-configured emergency contacts "
        "(EMERGENCY_CONTACT_CHAT_IDS). Use only when the user explicitly asks for help/an "
        "emergency alert to be sent — never on your own initiative."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "What's happening."},
            "latitude": {"type": "number", "description": "Optional location, if known."},
            "longitude": {"type": "number", "description": "Optional location, if known."},
        },
        "required": ["message"],
    }

    def run(self, message: str, latitude: float | None = None, longitude: float | None = None) -> str:
        if not (config.telegram_bot_token and config.emergency_contact_chat_ids):
            return "Emergency alerts are not configured (need TELEGRAM_BOT_TOKEN and EMERGENCY_CONTACT_CHAT_IDS)."

        chat_ids = [c.strip() for c in config.emergency_contact_chat_ids.split(",") if c.strip()]
        text = f"\U0001f6a8 EMERGENCY ALERT from {config.assistant_name}\n\n{message}"

        sent = []
        for chat_id in chat_ids:
            response = client.post(
                f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=10,
            )
            if response.status_code == 200:
                sent.append(chat_id)
                if latitude is not None and longitude is not None:
                    client.post(
                        f"https://api.telegram.org/bot{config.telegram_bot_token}/sendLocation",
                        json={"chat_id": chat_id, "latitude": latitude, "longitude": longitude},
                        timeout=10,
                    )

        if not sent:
            return "Failed to reach any emergency contacts."
        return f"Emergency alert sent to {len(sent)} contact(s)."
