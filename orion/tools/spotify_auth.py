"""OAuth helper for Spotify, mirroring tools/google_auth.py's pattern: first
run opens a browser to authorize, then a refresh token is cached on disk.

Requires a Spotify Premium account and a device with Spotify Connect active
(the Spotify app on your phone, or spotifyd running on the Pi) — the Web API
controls existing playback, it doesn't play audio itself.
"""
from __future__ import annotations

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from core.config import config

SCOPES = " ".join(
    [
        "user-modify-playback-state",
        "user-read-playback-state",
        "user-read-currently-playing",
        "playlist-read-private",
        "playlist-modify-private",
        "playlist-modify-public",
        "user-library-read",
    ]
)


def get_spotify_client() -> spotipy.Spotify:
    if not (config.spotify_client_id and config.spotify_client_secret):
        raise RuntimeError(
            "Spotify is not configured. Create an app at "
            "https://developer.spotify.com/dashboard and set SPOTIFY_CLIENT_ID / "
            "SPOTIFY_CLIENT_SECRET / SPOTIFY_REDIRECT_URI in .env."
        )

    auth_manager = SpotifyOAuth(
        client_id=config.spotify_client_id,
        client_secret=config.spotify_client_secret,
        redirect_uri=config.spotify_redirect_uri,
        scope=SCOPES,
        cache_path=config.spotify_token_path,
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth_manager)
