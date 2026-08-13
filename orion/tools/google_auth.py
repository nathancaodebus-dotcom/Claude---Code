"""Shared OAuth helper for Gmail + Calendar tools.

Uses the standard Google "installed app" flow: on first run it opens a
browser to authorize, then caches a refresh token on disk so Orion never
has to re-prompt. Both tools request their scopes on the same token file,
so you only authorize once.
"""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from core.config import config

# core/agent.py dispatches a turn's independent tool calls concurrently
# (e.g. 'check my email and what's on my calendar' fires search_emails and
# list_calendar_events at once) — without this, two threads hitting an
# expired/missing token at the same time could both read-check-refresh-
# write the same token file unsynchronized (duplicate network round trips,
# a last-write-wins race on the write itself), or, on a brand-new install
# with no token file yet, both open a separate local OAuth callback
# server/browser tab at once.
_lock = threading.Lock()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    # .modify covers labeling/archiving/trashing — deliberately NOT gmail.send,
    # so Orion can triage your inbox but can never send mail on its own.
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/contacts",
]


def _write_token_file(path: Path, content: str) -> None:
    """Writes via a temp file + atomic rename, chmod'd 0600 before it's
    ever visible at the real path — this file holds a live OAuth refresh
    token. write_text() directly used to (a) inherit the process umask,
    commonly leaving it group/world-readable, and (b) leave a truncated,
    corrupt file behind if the process died between open and write
    (plausible on a Pi, per this project's own target hardware), forcing a
    confusing re-auth or an unhandled parse error on the next read."""
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


def get_credentials() -> Credentials:
    with _lock:
        token_path = Path(config.google_token_path)
        creds: Credentials | None = None

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                creds_path = Path(config.google_credentials_path)
                if not creds_path.exists():
                    raise RuntimeError(
                        f"Google credentials file not found at {creds_path}. "
                        "Download an OAuth client (Desktop app) from Google Cloud Console "
                        "for the Gmail API and Calendar API, and point "
                        "GOOGLE_CREDENTIALS_PATH at it."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
                creds = flow.run_local_server(port=0)

            _write_token_file(token_path, creds.to_json())

        return creds
