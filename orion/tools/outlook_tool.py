"""Read, search, and draft in the user's Outlook mail via Microsoft Graph —
mirrors tools/gmail_tool.py's shape for the Microsoft side of the account.

Never sends mail: create_outlook_email_draft only creates a saved draft,
matching Gmail's boundary and tools/microsoft_auth.py's scope selection
(Mail.Send is deliberately not requested).
"""
from __future__ import annotations

import httpx

from core.http import client
from tools.base import Tool
from tools.microsoft_auth import get_access_token

_GRAPH = "https://graph.microsoft.com/v1.0"


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    if extra:
        headers.update(extra)
    return headers


class OutlookSearchTool(Tool):
    name = "search_outlook_emails"
    description = (
        "Search the user's Outlook inbox. Pass a query for full-text search (matches subject, "
        "sender, and body), or omit it to list unread mail. Returns subject, sender, date and a "
        "preview for each matching email."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Free-text search query. Omit for unread mail."},
            "max_results": {
                "type": "integer",
                "description": "Maximum number of emails to return (default 10).",
            },
        },
    }

    def run(self, query: str | None = None, max_results: int = 10) -> str:
        params: dict[str, object] = {
            "$top": max_results,
            "$select": "id,subject,from,receivedDateTime,bodyPreview",
        }
        if query:
            params["$search"] = f'"{query}"'
        else:
            params["$filter"] = "isRead eq false"
            params["$orderby"] = "receivedDateTime desc"

        response = client.get(f"{_GRAPH}/me/messages", headers=_headers(), params=params, timeout=15)
        response.raise_for_status()
        messages = response.json().get("value", [])
        if not messages:
            return "No matching emails found."

        lines = []
        for msg in messages:
            sender = msg.get("from", {}).get("emailAddress", {}).get("address", "?")
            lines.append(
                f"- id: {msg['id']} | From: {sender} | Subject: {msg.get('subject', '(no subject)')} "
                f"| Date: {msg.get('receivedDateTime', '?')} | {msg.get('bodyPreview', '')}"
            )
        return "\n".join(lines)


class OutlookReadTool(Tool):
    name = "read_outlook_email"
    description = "Read the full body of a specific Outlook email by its message id (from search_outlook_emails results)."
    input_schema = {
        "type": "object",
        "properties": {"message_id": {"type": "string"}},
        "required": ["message_id"],
    }

    def run(self, message_id: str) -> str:
        response = client.get(
            f"{_GRAPH}/me/messages/{message_id}",
            headers=_headers({"Prefer": 'outlook.body-content-type="text"'}),
            params={"$select": "subject,from,receivedDateTime,body"},
            timeout=15,
        )
        response.raise_for_status()
        msg = response.json()
        sender = msg.get("from", {}).get("emailAddress", {}).get("address", "?")
        body = msg.get("body", {}).get("content", "")
        return (
            f"From: {sender}\n"
            f"Subject: {msg.get('subject', '(no subject)')}\n"
            f"Date: {msg.get('receivedDateTime', '?')}\n\n"
            f"{body}"
        )


class OutlookCreateDraftTool(Tool):
    name = "create_outlook_email_draft"
    description = (
        "Create a draft email in Outlook (does not send it) — use this when the user dictates "
        "or asks for an email to be drafted. They can review and send it themselves."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address."},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    }

    def run(self, to: str, subject: str, body: str) -> str:
        payload = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }
        # POST /me/messages saves a draft — sending requires a separate,
        # never-called /send request, same boundary as Gmail's draft tool.
        response = client.post(f"{_GRAPH}/me/messages", headers=_headers(), json=payload, timeout=15)
        response.raise_for_status()
        draft = response.json()
        return f"Draft created (id={draft['id']}) to {to}: \"{subject}\". Not sent — review it in Outlook."


class OutlookArchiveTool(Tool):
    name = "archive_outlook_email"
    description = "Archive an Outlook email (moves it out of the inbox into Archive), by message id."
    input_schema = {
        "type": "object",
        "properties": {"message_id": {"type": "string"}},
        "required": ["message_id"],
    }

    def run(self, message_id: str) -> str:
        response = client.post(
            f"{_GRAPH}/me/messages/{message_id}/move",
            headers=_headers(),
            json={"destinationId": "archive"},
            timeout=15,
        )
        response.raise_for_status()
        return f"Archived email {message_id}."


class OutlookMarkReadTool(Tool):
    name = "mark_outlook_email_read"
    description = "Mark an Outlook email as read, by message id."
    input_schema = {
        "type": "object",
        "properties": {"message_id": {"type": "string"}},
        "required": ["message_id"],
    }

    def run(self, message_id: str) -> str:
        response = client.patch(
            f"{_GRAPH}/me/messages/{message_id}", headers=_headers(), json={"isRead": True}, timeout=15
        )
        response.raise_for_status()
        return f"Marked email {message_id} as read."


class OutlookUnreadCountTool(Tool):
    name = "count_unread_outlook_emails"
    description = "Get the number of unread emails in the Outlook inbox (fast overview without listing them all)."
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        response = client.get(
            f"{_GRAPH}/me/mailFolders/inbox",
            headers=_headers(),
            params={"$select": "unreadItemCount"},
            timeout=15,
        )
        response.raise_for_status()
        count = response.json().get("unreadItemCount", 0)
        return f"{count} unread email(s)."
