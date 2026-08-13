"""Get song lyrics — lyrics.ovh is free and keyless, but only returns plain
untimed lyrics (no synced/karaoke timing; no free API offers that reliably)."""
from __future__ import annotations

from urllib.parse import quote

import httpx

from core.http import client
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
        # artist/title are interpolated as URL *path segments* — an
        # unescaped '/' in either (e.g. artist='AC/DC') turns into an extra
        # path segment instead of a literal character, so the API sees
        # 'AC', 'DC', title as three segments instead of {artist}/{title},
        # 404s, and this tool reports "no lyrics found" for a song that
        # obviously has some. quote() with the default safe='/' would still
        # let a literal '/' through unescaped, so it's excluded here.
        url = f"https://api.lyrics.ovh/v1/{quote(artist, safe='')}/{quote(title, safe='')}"
        response = client.get(url, timeout=10)
        if response.status_code != 200:
            return f"No lyrics found for '{title}' by {artist}."
        return response.json().get("lyrics", "No lyrics found.").strip()
