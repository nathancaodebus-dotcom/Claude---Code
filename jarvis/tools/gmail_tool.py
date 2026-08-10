"""Read, search, and draft in the user's Gmail inbox."""
from __future__ import annotations

import base64
from email.mime.text import MIMEText

from googleapiclient.discovery import build

from tools.base import Tool
from tools.google_auth import get_credentials


def _extract_snippet(message: dict) -> str:
    return message.get("snippet", "")


def _extract_body(message: dict) -> str:
    payload = message.get("payload", {})
    parts = payload.get("parts") or [payload]
    for part in parts:
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    return _extract_snippet(message)


class GmailSearchTool(Tool):
    name = "search_emails"
    description = (
        "Search the user's Gmail inbox using Gmail search syntax "
        "(e.g. 'is:unread', 'from:boss@company.com', 'subject:invoice newer_than:7d'). "
        "Returns subject, sender, date and a snippet for each matching email."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Gmail search query. Defaults to 'is:unread' if omitted.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of emails to return (default 10).",
            },
        },
    }

    def run(self, query: str = "is:unread", max_results: int = 10) -> str:
        service = build("gmail", "v1", credentials=get_credentials())
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        message_refs = results.get("messages", [])
        if not message_refs:
            return "No matching emails found."

        lines = []
        for ref in message_refs:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=ref["id"], format="metadata",
                     metadataHeaders=["From", "Subject", "Date"])
                .execute()
            )
            headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
            lines.append(
                f"- id: {ref['id']} | From: {headers.get('From', '?')} | Subject: {headers.get('Subject', '(no subject)')} "
                f"| Date: {headers.get('Date', '?')} | {msg.get('snippet', '')}"
            )
        return "\n".join(lines)


class GmailReadTool(Tool):
    name = "read_email"
    description = "Read the full body of a specific email by its Gmail message id (from search_emails results)."
    input_schema = {
        "type": "object",
        "properties": {"message_id": {"type": "string"}},
        "required": ["message_id"],
    }

    def run(self, message_id: str) -> str:
        service = build("gmail", "v1", credentials=get_credentials())
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        body = _extract_body(msg)
        return (
            f"From: {headers.get('From', '?')}\n"
            f"Subject: {headers.get('Subject', '(no subject)')}\n"
            f"Date: {headers.get('Date', '?')}\n\n"
            f"{body}"
        )


class GmailCreateDraftTool(Tool):
    name = "create_email_draft"
    description = (
        "Create a draft email in Gmail (does not send it) — use this when the user dictates "
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
        service = build("gmail", "v1", credentials=get_credentials())

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        draft = (
            service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw}})
            .execute()
        )
        return f"Draft created (id={draft['id']}) to {to}: \"{subject}\". Not sent — review it in Gmail."


class GmailArchiveTool(Tool):
    name = "archive_email"
    description = "Archive an email (removes it from the inbox, doesn't delete it), by message id."
    input_schema = {
        "type": "object",
        "properties": {"message_id": {"type": "string"}},
        "required": ["message_id"],
    }

    def run(self, message_id: str) -> str:
        service = build("gmail", "v1", credentials=get_credentials())
        service.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["INBOX"]}
        ).execute()
        return f"Archived email {message_id}."


class GmailMarkReadTool(Tool):
    name = "mark_email_read"
    description = "Mark an email as read, by message id."
    input_schema = {
        "type": "object",
        "properties": {"message_id": {"type": "string"}},
        "required": ["message_id"],
    }

    def run(self, message_id: str) -> str:
        service = build("gmail", "v1", credentials=get_credentials())
        service.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()
        return f"Marked email {message_id} as read."


class GmailUnreadCountTool(Tool):
    name = "count_unread_emails"
    description = "Get the number of unread emails in the inbox (fast overview without listing them all)."
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        service = build("gmail", "v1", credentials=get_credentials())
        results = service.users().messages().list(userId="me", q="is:unread", maxResults=500).execute()
        count = results.get("resultSizeEstimate", len(results.get("messages", [])))
        return f"{count} unread email(s)."
