"""Shared OAuth helper for Outlook Mail/Calendar/Contacts tools (Microsoft
Graph API) — mirrors tools/google_auth.py's role for Gmail/Calendar, added
alongside it rather than replacing it.

Uses MSAL's device code flow rather than Google's local-server browser
flow: this typically runs headless (a Raspberry Pi with no browser of its
own), so on first run it prints a URL and a short code to enter from *any*
device (phone, laptop) instead of needing a browser on the same machine.
The resulting token is cached on disk so Orion never has to re-prompt.

Scopes deliberately exclude Mail.Send — the same "drafts and triages, never
auto-sends" boundary tools/google_auth.py already draws for Gmail, kept
consistent here rather than being a Microsoft-specific inconsistency.
"""
from __future__ import annotations

from pathlib import Path

import msal

from core.config import config

SCOPES = ["Mail.Read", "Mail.ReadWrite", "Calendars.ReadWrite", "Contacts.ReadWrite"]
_AUTHORITY = "https://login.microsoftonline.com/common"


def get_access_token() -> str:
    if not config.microsoft_client_id:
        raise RuntimeError(
            "MICROSOFT_CLIENT_ID is not set. Register a public-client app in Azure AD/Entra ID "
            "(no client secret needed — device code flow doesn't use one) and set its "
            "Application (client) ID as MICROSOFT_CLIENT_ID."
        )

    token_path = Path(config.microsoft_token_path)
    cache = msal.SerializableTokenCache()
    if token_path.exists():
        cache.deserialize(token_path.read_text())

    app = msal.PublicClientApplication(
        config.microsoft_client_id, authority=_AUTHORITY, token_cache=cache
    )

    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Could not start the Microsoft sign-in flow: {flow}")
        print(flow["message"])  # e.g. "To sign in, visit https://microsoft.com/devicelogin and enter code ABCD1234"
        result = app.acquire_token_by_device_flow(flow)

    if cache.has_state_changed:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(cache.serialize())

    if not result or "access_token" not in result:
        error = (result or {}).get("error_description", "no token returned")
        raise RuntimeError(f"Microsoft authentication failed: {error}")

    return result["access_token"]
