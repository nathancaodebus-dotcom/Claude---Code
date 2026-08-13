"""List and create Google Calendar events."""
from __future__ import annotations

import datetime as dt

from googleapiclient.discovery import build

from tools.base import Tool
from tools.google_auth import get_credentials


class ListEventsTool(Tool):
    name = "list_calendar_events"
    description = "List the user's upcoming calendar events within the next N days (default 7)."
    input_schema = {
        "type": "object",
        "properties": {
            "days_ahead": {"type": "integer", "description": "How many days ahead to look (default 7)."},
        },
    }

    def run(self, days_ahead: int = 7) -> str:
        service = build("calendar", "v3", credentials=get_credentials())
        now = dt.datetime.utcnow().isoformat() + "Z"
        end = (dt.datetime.utcnow() + dt.timedelta(days=days_ahead)).isoformat() + "Z"
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                timeMax=end,
                singleEvents=True,
                orderBy="startTime",
                maxResults=25,
            )
            .execute()
        )
        events = events_result.get("items", [])
        if not events:
            return "No upcoming events."

        lines = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            lines.append(f"- [{event['id']}] {start}: {event.get('summary', '(no title)')}")
        return "\n".join(lines)


class CreateEventTool(Tool):
    name = "create_calendar_event"
    description = "Create a new event on the user's primary Google Calendar."
    input_schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Event title."},
            "start_iso": {
                "type": "string",
                "description": "Start time in ISO 8601 with timezone offset, e.g. '2026-08-12T14:00:00-04:00'.",
            },
            "end_iso": {
                "type": "string",
                "description": "End time in ISO 8601 with timezone offset. If omitted, defaults to 1 hour after start.",
            },
            "description": {"type": "string", "description": "Optional event description."},
        },
        "required": ["summary", "start_iso"],
    }

    def run(self, summary: str, start_iso: str, end_iso: str | None = None, description: str = "") -> str:
        service = build("calendar", "v3", credentials=get_credentials())

        if not end_iso:
            start_dt = dt.datetime.fromisoformat(start_iso)
            end_iso = (start_dt + dt.timedelta(hours=1)).isoformat()

        event_body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
        }
        created = service.events().insert(calendarId="primary", body=event_body).execute()
        return f"Event created: {created.get('summary')} at {start_iso} (id={created.get('id')})"
