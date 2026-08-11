"""Search and add contacts via the Google People API, reusing the same
OAuth token as Gmail/Calendar (tools/google_auth.py already requests the
contacts scope)."""
from __future__ import annotations

from googleapiclient.discovery import build

from tools.base import Tool
from tools.google_auth import get_credentials


class SearchContactsTool(Tool):
    name = "search_contacts"
    description = "Search the user's Google contacts by name."
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }

    def run(self, query: str) -> str:
        service = build("people", "v1", credentials=get_credentials())
        results = service.people().searchContacts(
            query=query, readMask="names,emailAddresses,phoneNumbers"
        ).execute()

        matches = results.get("results", [])
        if not matches:
            return f"No contacts found matching '{query}'."

        lines = []
        for match in matches:
            person = match["person"]
            name = person.get("names", [{}])[0].get("displayName", "(no name)")
            emails = ", ".join(e["value"] for e in person.get("emailAddresses", []))
            phones = ", ".join(p["value"] for p in person.get("phoneNumbers", []))
            lines.append(f"- {name} | {emails} | {phones}")
        return "\n".join(lines)


class AddContactTool(Tool):
    name = "add_contact"
    description = "Add a new contact to the user's Google contacts."
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "email": {"type": "string"},
            "phone": {"type": "string"},
        },
        "required": ["name"],
    }

    def run(self, name: str, email: str | None = None, phone: str | None = None) -> str:
        service = build("people", "v1", credentials=get_credentials())

        body = {"names": [{"givenName": name}]}
        if email:
            body["emailAddresses"] = [{"value": email}]
        if phone:
            body["phoneNumbers"] = [{"value": phone}]

        service.people().createContact(body=body).execute()
        return f"Added contact: {name}"
