"""Shared OAuth helper for Gmail + Calendar tools.

Uses the standard Google "installed app" flow: on first run it opens a
browser to authorize, then caches a refresh token on disk so Jarvis never
has to re-prompt. Both tools request their scopes on the same token file,
so you only authorize once.
"""
from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from core.config import config

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/contacts",
]


def get_credentials() -> Credentials:
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

        token_path.write_text(creds.to_json())

    return creds
