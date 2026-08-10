"""Generic CalDAV calendar bridge — covers Outlook, iCloud, Nextcloud, or any
other CalDAV-speaking calendar with one integration instead of one per
provider. Complements the native Google Calendar tools (calendar_tool.py),
which use Google's own richer API.

iCloud: use an app-specific password (appleid.apple.com) with
CALDAV_URL=https://caldav.icloud.com.
Outlook: Microsoft's CalDAV support is limited/being phased out in favor of
Graph API — if it doesn't work for your account, ask for a dedicated
Outlook/Graph integration instead.
"""
from __future__ import annotations

import datetime as dt

import caldav

from core.config import config
from tools.base import Tool


def _client() -> caldav.DAVClient:
    if not (config.caldav_url and config.caldav_username and config.caldav_password):
        raise RuntimeError(
            "CalDAV is not configured. Set CALDAV_URL, CALDAV_USERNAME, and CALDAV_PASSWORD in .env."
        )
    return caldav.DAVClient(
        url=config.caldav_url, username=config.caldav_username, password=config.caldav_password
    )


class ListCaldavEventsTool(Tool):
    name = "list_caldav_events"
    description = (
        "List upcoming events from a CalDAV calendar (Outlook, iCloud, Nextcloud, etc. — "
        "for Google Calendar use list_calendar_events instead)."
    )
    input_schema = {
        "type": "object",
        "properties": {"days_ahead": {"type": "integer", "description": "Default 7."}},
    }

    def run(self, days_ahead: int = 7) -> str:
        client = _client()
        principal = client.principal()
        now = dt.datetime.now()
        end = now + dt.timedelta(days=days_ahead)

        lines = []
        for calendar in principal.calendars():
            for event in calendar.search(start=now, end=end, event=True, expand=True):
                component = event.icalendar_component
                summary = str(component.get("summary", "(no title)"))
                start = component.get("dtstart").dt
                lines.append(f"- [{calendar.name}] {start}: {summary}")

        return "\n".join(lines) if lines else "No upcoming CalDAV events."


class CreateCaldavEventTool(Tool):
    name = "create_caldav_event"
    description = "Create a new event on a CalDAV calendar (Outlook, iCloud, Nextcloud, etc.)."
    input_schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "start_iso": {"type": "string", "description": "ISO 8601 datetime with timezone offset."},
            "end_iso": {"type": "string", "description": "Defaults to 1 hour after start if omitted."},
            "calendar_name": {
                "type": "string",
                "description": "Which calendar to add it to. Defaults to the first available.",
            },
        },
        "required": ["summary", "start_iso"],
    }

    def run(self, summary: str, start_iso: str, end_iso: str | None = None, calendar_name: str | None = None) -> str:
        client = _client()
        principal = client.principal()
        calendars = principal.calendars()
        if not calendars:
            return "No CalDAV calendars found for this account."

        target = calendars[0]
        if calendar_name:
            matches = [c for c in calendars if c.name and c.name.lower() == calendar_name.lower()]
            if not matches:
                return f"No calendar named '{calendar_name}'. Available: {[c.name for c in calendars]}"
            target = matches[0]

        start = dt.datetime.fromisoformat(start_iso)
        end = dt.datetime.fromisoformat(end_iso) if end_iso else start + dt.timedelta(hours=1)

        target.save_event(dtstart=start, dtend=end, summary=summary)
        return f"Created '{summary}' on '{target.name}' at {start_iso}."
