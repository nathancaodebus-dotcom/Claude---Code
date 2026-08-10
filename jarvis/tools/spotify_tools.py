"""Control Spotify playback: search and play tracks/albums/playlists, pause,
skip, adjust volume. Controls whatever device is currently active in Spotify
Connect (phone, speaker, or spotifyd running on the Pi) — this is the Web
API's job, it doesn't stream audio itself, so a Premium account and an
active device are required."""
from __future__ import annotations

from tools.base import Tool
from tools.spotify_auth import get_spotify_client


class SearchSpotifyTool(Tool):
    name = "search_spotify"
    description = "Search Spotify for tracks, albums, artists, or playlists."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "search_type": {
                "type": "string",
                "enum": ["track", "album", "artist", "playlist"],
                "description": "Default 'track'.",
            },
            "max_results": {"type": "integer", "description": "Default 5."},
        },
        "required": ["query"],
    }

    def run(self, query: str, search_type: str = "track", max_results: int = 5) -> str:
        client = get_spotify_client()
        results = client.search(q=query, type=search_type, limit=max_results)
        items = results[f"{search_type}s"]["items"]
        if not items:
            return "No results found."

        lines = []
        for item in items:
            if search_type == "artist":
                lines.append(f"- {item['name']} (uri={item['uri']})")
            else:
                artists = ", ".join(a["name"] for a in item.get("artists", [])) or item.get("owner", {}).get("display_name", "")
                lines.append(f"- {item['name']} — {artists} (uri={item['uri']})")
        return "\n".join(lines)


class PlaySpotifyTool(Tool):
    name = "play_spotify"
    description = (
        "Play a track, album, or playlist on Spotify. Provide either a search query "
        "(the first matching track will play) or a specific Spotify uri from search_spotify."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search terms, e.g. 'Bohemian Rhapsody Queen'."},
            "uri": {"type": "string", "description": "A specific Spotify uri, e.g. 'spotify:track:...'."},
            "device_name": {"type": "string", "description": "Target device name. Uses the active device if omitted."},
        },
    }

    def run(self, query: str | None = None, uri: str | None = None, device_name: str | None = None) -> str:
        client = get_spotify_client()
        device_id = self._resolve_device(client, device_name)

        if uri:
            target_uri, label = uri, uri
        elif query:
            results = client.search(q=query, type="track", limit=1)
            items = results["tracks"]["items"]
            if not items:
                return f"No track found for '{query}'."
            target_uri = items[0]["uri"]
            label = f"{items[0]['name']} — {', '.join(a['name'] for a in items[0]['artists'])}"
        else:
            raise ValueError("Provide either query or uri.")

        if target_uri.startswith("spotify:track:"):
            client.start_playback(device_id=device_id, uris=[target_uri])
        else:
            client.start_playback(device_id=device_id, context_uri=target_uri)

        return f"Playing {label} on Spotify."

    @staticmethod
    def _resolve_device(client, device_name: str | None) -> str | None:
        if not device_name:
            return None
        devices = client.devices()["devices"]
        for device in devices:
            if device["name"].lower() == device_name.lower():
                return device["id"]
        raise ValueError(f"No Spotify Connect device named '{device_name}' found.")


class PauseSpotifyTool(Tool):
    name = "pause_spotify"
    description = "Pause Spotify playback."
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        get_spotify_client().pause_playback()
        return "Paused."


class ResumeSpotifyTool(Tool):
    name = "resume_spotify"
    description = "Resume paused Spotify playback."
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        get_spotify_client().start_playback()
        return "Resumed."


class SkipSpotifyTool(Tool):
    name = "skip_spotify_track"
    description = "Skip to the next or previous track on Spotify."
    input_schema = {
        "type": "object",
        "properties": {"direction": {"type": "string", "enum": ["next", "previous"]}},
        "required": ["direction"],
    }

    def run(self, direction: str) -> str:
        client = get_spotify_client()
        if direction == "next":
            client.next_track()
        else:
            client.previous_track()
        return f"Skipped to {direction} track."


class SetSpotifyVolumeTool(Tool):
    name = "set_spotify_volume"
    description = "Set Spotify playback volume (0-100)."
    input_schema = {
        "type": "object",
        "properties": {"volume_percent": {"type": "integer"}},
        "required": ["volume_percent"],
    }

    def run(self, volume_percent: int) -> str:
        get_spotify_client().volume(max(0, min(100, volume_percent)))
        return f"Volume set to {volume_percent}%."


class ListSpotifyDevicesTool(Tool):
    name = "list_spotify_devices"
    description = "List available Spotify Connect devices (phone, speaker, spotifyd on the Pi, etc.)."
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        devices = get_spotify_client().devices()["devices"]
        if not devices:
            return "No active Spotify Connect devices found. Open Spotify on a device first."
        return "\n".join(
            f"- {d['name']} ({d['type']}){' [active]' if d['is_active'] else ''}" for d in devices
        )
