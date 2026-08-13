"""List and create Outlook Calendar events via Microsoft Graph — mirrors
tools/calendar_tool.py's shape for the Microsoft side of the account."""
from __future__ import annotations

import datetime as dt

import httpx

from core.http import client
from tools.base import Tool
from tools.microsoft_auth import get_access_token

_GRAPH = "https://graph.microsoft.com/v1.0"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_access_token()}"}


class ListOutlookEventsTool(Tool):
    name = "list_outlook_calendar_events"
    description = "List the user's upcoming Outlook calendar events within the next N days (default 7)."
    input_schema = {
        "type": "object",
        "properties": {
            "days_ahead": {"type": "integer", "description": "How many days ahead to look (default 7)."},
        },
    }

    def run(self, days_ahead: int = 7) -> str:
        now = dt.datetime.utcnow()
        end = now + dt.timedelta(days=days_ahead)
        response = client.get(
            f"{_GRAPH}/me/calendarview",
            headers={**_headers(), "Prefer": 'outlook.timezone="UTC"'},
            params={
                "startDateTime": now.isoformat() + "Z",
                "endDateTime": end.isoformat() + "Z",
                "$orderby": "start/dateTime",
                "$top": 25,
            },
            timeout=15,
        )
        response.raise_for_status()
        events = response.json().get("value", [])
        if not events:
            return "No upcoming events."

        lines = []
        for event in events:
            start = event.get("start", {}).get("dateTime", "?")
            lines.append(f"- [{event['id']}] {start}: {event.get('subject', '(no title)')}")
        return "\n".join(lines)


class CreateOutlookEventTool(Tool):
    name = "create_outlook_calendar_event"
    description = "Create a new event on the user's Outlook calendar."
    input_schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Event title."},
            "start_iso": {
                "type": "string",
                "description": "Start time in ISO 8601, e.g. '2026-08-12T14:00:00'.",
            },
            "end_iso": {
                "type": "string",
                "description": "End time in ISO 8601. If omitted, defaults to 1 hour after start.",
            },
            "description": {"type": "string", "description": "Optional event description."},
        },
        "required": ["summary", "start_iso"],
    }

    def run(self, summary: str, start_iso: str, end_iso: str | None = None, description: str = "") -> str:
        if not end_iso:
            start_dt = dt.datetime.fromisoformat(start_iso)
            end_iso = (start_dt + dt.timedelta(hours=1)).isoformat()

        payload = {
            "subject": summary,
            "body": {"contentType": "Text", "content": description},
            "start": {"dateTime": start_iso, "timeZone": "UTC"},
            "end": {"dateTime": end_iso, "timeZone": "UTC"},
        }
        response = client.post(f"{_GRAPH}/me/events", headers=_headers(), json=payload, timeout=15)
        response.raise_for_status()
        created = response.json()
        return f"Event created: {created.get('subject')} at {start_iso} (id={created.get('id')})"
