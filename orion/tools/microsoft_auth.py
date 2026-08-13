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

import os
import tempfile
import threading
from pathlib import Path

import msal

from core.config import config

SCOPES = ["Mail.Read", "Mail.ReadWrite", "Calendars.ReadWrite", "Contacts.ReadWrite"]
_AUTHORITY = "https://login.microsoftonline.com/common"

# Same reasoning as tools/google_auth.py's _lock: core/agent.py dispatches
# a turn's tool calls concurrently, and without this, two threads hitting
# a not-yet-cached token at once could both start an independent device
# code flow — printing two different codes and blocking two worker threads
# on human input at once.
_lock = threading.Lock()


def _write_token_file(path: Path, content: str) -> None:
    """Same reasoning as tools/google_auth.py's identical helper: atomic
    (temp file + rename) and chmod'd 0600 before it's ever visible at the
    real path, rather than a plain write_text() that inherits the process
    umask and can leave a truncated file behind on a crash mid-write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    except BaseException:
        os.unlink(tmp_name)
        raise


def get_access_token() -> str:
    if not config.microsoft_client_id:
        raise RuntimeError(
            "MICROSOFT_CLIENT_ID is not set. Register a public-client app in Azure AD/Entra ID "
            "(no client secret needed — device code flow doesn't use one) and set its "
            "Application (client) ID as MICROSOFT_CLIENT_ID."
        )

    with _lock:
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
            _write_token_file(token_path, cache.serialize())

        if not result or "access_token" not in result:
            error = (result or {}).get("error_description", "no token returned")
            raise RuntimeError(f"Microsoft authentication failed: {error}")

        return result["access_token"]
