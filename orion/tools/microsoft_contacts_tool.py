"""Search and add contacts via Microsoft Graph, reusing the same OAuth
token as Outlook Mail/Calendar (tools/microsoft_auth.py already requests
the contacts scope)."""
from __future__ import annotations

import httpx

from core.http import client
from tools.base import Tool
from tools.microsoft_auth import get_access_token

_GRAPH = "https://graph.microsoft.com/v1.0"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_access_token()}"}


class SearchOutlookContactsTool(Tool):
    name = "search_outlook_contacts"
    description = "Search the user's Outlook contacts by name."
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }

    def run(self, query: str) -> str:
        escaped = query.replace("'", "''")
        response = client.get(
            f"{_GRAPH}/me/contacts",
            headers=_headers(),
            params={
                "$filter": f"startswith(displayName,'{escaped}')",
                "$select": "displayName,emailAddresses,businessPhones,mobilePhone",
            },
            timeout=15,
        )
        response.raise_for_status()
        matches = response.json().get("value", [])
        if not matches:
            return f"No contacts found matching '{query}'."

        lines = []
        for person in matches:
            name = person.get("displayName", "(no name)")
            emails = ", ".join(e["address"] for e in person.get("emailAddresses", []))
            phones = list(person.get("businessPhones", []))
            if person.get("mobilePhone"):
                phones.append(person["mobilePhone"])
            lines.append(f"- {name} | {emails} | {', '.join(phones)}")
        return "\n".join(lines)


class AddOutlookContactTool(Tool):
    name = "add_outlook_contact"
    description = "Add a new contact to the user's Outlook contacts."
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
        payload: dict[str, object] = {"givenName": name}
        if email:
            payload["emailAddresses"] = [{"address": email, "name": name}]
        if phone:
            payload["mobilePhone"] = phone

        response = client.post(f"{_GRAPH}/me/contacts", headers=_headers(), json=payload, timeout=15)
        response.raise_for_status()
        return f"Added contact: {name}"
