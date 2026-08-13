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


def _to_utc_naive_iso(iso_string: str) -> str:
    """Graph's event dateTime field is a naive local-time string paired
    separately with a timeZone name (see the 'timeZone': 'UTC' below) — it
    does NOT accept an embedded UTC offset the way Google Calendar's API
    does. This used to just pass start_iso straight through with
    timeZone hardcoded to UTC regardless of what offset (if any) the
    caller's string actually carried, so '2026-08-12T14:00:00' (a plausible
    local wall-clock time, matching tools/calendar_tool.py's own example
    format before it required an offset) got silently created as 14:00
    *UTC* — several hours off from whatever the caller meant anywhere west
    of Greenwich. Requiring and converting a real UTC offset here (raising
    on a genuinely ambiguous naive input rather than guessing) makes this
    tool's contract match tools/calendar_tool.py's Google equivalent."""
    parsed = dt.datetime.fromisoformat(iso_string)
    if parsed.tzinfo is None:
        raise ValueError(
            f"'{iso_string}' has no UTC offset — pass one explicitly (e.g. '...-04:00'), "
            "a bare local time here is ambiguous."
        )
    return parsed.astimezone(dt.timezone.utc).replace(tzinfo=None).isoformat()


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
                "description": "Start time in ISO 8601 with UTC offset, e.g. '2026-08-12T14:00:00-04:00'.",
            },
            "end_iso": {
                "type": "string",
                "description": "End time in ISO 8601 with UTC offset. If omitted, defaults to 1 hour after start.",
            },
            "description": {"type": "string", "description": "Optional event description."},
        },
        "required": ["summary", "start_iso"],
    }

    def run(self, summary: str, start_iso: str, end_iso: str | None = None, description: str = "") -> str:
        start_dt = dt.datetime.fromisoformat(start_iso)
        if not end_iso:
            end_iso = (start_dt + dt.timedelta(hours=1)).isoformat()

        payload = {
            "subject": summary,
            "body": {"contentType": "Text", "content": description},
            "start": {"dateTime": _to_utc_naive_iso(start_iso), "timeZone": "UTC"},
            "end": {"dateTime": _to_utc_naive_iso(end_iso), "timeZone": "UTC"},
        }
        response = client.post(f"{_GRAPH}/me/events", headers=_headers(), json=payload, timeout=15)
        response.raise_for_status()
        created = response.json()
        return f"Event created: {created.get('subject')} at {start_iso} (id={created.get('id')})"
