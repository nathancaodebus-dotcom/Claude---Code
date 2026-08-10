"""Get song lyrics — lyrics.ovh is free and keyless, but only returns plain
untimed lyrics (no synced/karaoke timing; no free API offers that reliably)."""
from __future__ import annotations

import httpx

from tools.base import Tool


class GetLyricsTool(Tool):
    name = "get_lyrics"
    description = "Get the lyrics for a song by artist and title. Untimed lyrics only, no karaoke sync."
    input_schema = {
        "type": "object",
        "properties": {"artist": {"type": "string"}, "title": {"type": "string"}},
        "required": ["artist", "title"],
    }

    def run(self, artist: str, title: str) -> str:
        response = httpx.get(f"https://api.lyrics.ovh/v1/{artist}/{title}", timeout=10)
        if response.status_code != 200:
            return f"No lyrics found for '{title}' by {artist}."
        return response.json().get("lyrics", "No lyrics found.").strip()
