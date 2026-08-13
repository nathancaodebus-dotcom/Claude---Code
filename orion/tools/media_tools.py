"""YouTube search + casting to a Chromecast/Google TV device, and launching
streaming apps (Netflix, Disney+, Spotify, YouTube Music) on the TV.

Important limitation, stated plainly: Netflix and Disney+ publish no public
API for search or playback control, so Orion can only *launch their app* on
the Chromecast (exactly what casting from your phone does) — it cannot pick
a specific title for you inside those apps. YouTube is different: Google
documents an official Cast controller for it, so search + 'play this
specific video' both work for real.

Chromecast app ids below are the values that have circulated in open-source
Cast tooling (e.g. the `catt` project) for years; Google doesn't publish a
stable registry, so if one stops working, override it via the
CHROMECAST_APP_IDS env var (JSON, e.g. '{"netflix": "XXXXXXXX"}').
"""
from __future__ import annotations

import json
import os

import pychromecast
from googleapiclient.discovery import build

from core.config import config
from tools.base import Tool

_DEFAULT_APP_IDS = {
    "youtube": "233637DE",
    "netflix": "CA5E8412",
    "spotify": "CC32E753",
    "disney_plus": "C3DE6A2A",
    "youtube_music": "9AC194DC",
}


def _known_app_ids() -> dict[str, str]:
    app_ids = dict(_DEFAULT_APP_IDS)
    override = os.getenv("CHROMECAST_APP_IDS")
    if override:
        app_ids.update(json.loads(override))
    return app_ids


def _get_chromecast(device_name: str | None = None):
    device_name = device_name or config.chromecast_name
    if not device_name:
        raise RuntimeError(
            "No Chromecast device specified. Set CHROMECAST_NAME in .env, or pass "
            "device_name explicitly (see list_chromecasts)."
        )
    chromecasts, browser = pychromecast.get_chromecasts()
    try:
        for cc in chromecasts:
            if cc.name.lower() == device_name.lower():
                cc.wait()
                return cc
        raise RuntimeError(f"No Chromecast named '{device_name}' found on the network.")
    finally:
        pychromecast.discovery.stop_discovery(browser)


class ListChromecastsTool(Tool):
    name = "list_chromecasts"
    description = "Discover Chromecast/Google TV devices available on the local network."
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        chromecasts, browser = pychromecast.get_chromecasts()
        pychromecast.discovery.stop_discovery(browser)
        if not chromecasts:
            return "No Chromecast devices found on the network."
        return "\n".join(f"- {cc.name} ({cc.model_name})" for cc in chromecasts)


class LaunchAppOnTvTool(Tool):
    name = "launch_app_on_tv"
    description = (
        "Launch an app (netflix, disney_plus, spotify, youtube, youtube_music, or a raw "
        "Chromecast app id) on the Chromecast/TV — the same as casting from your phone. "
        "For Netflix/Disney+ this only opens the app; it can't pick a specific title. "
        "For YouTube, prefer play_youtube_video to jump straight to a video."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "app": {"type": "string", "description": "One of the known app names, or a raw app id."},
            "device_name": {"type": "string", "description": "Defaults to CHROMECAST_NAME."},
        },
        "required": ["app"],
    }

    def run(self, app: str, device_name: str | None = None) -> str:
        app_id = _known_app_ids().get(app.lower(), app)
        cc = _get_chromecast(device_name)
        cc.start_app(app_id)
        return f"Launched {app} on {cc.name}."


class StopCastingTool(Tool):
    name = "stop_casting"
    description = "Stop whatever is currently playing/casting on the TV."
    input_schema = {
        "type": "object",
        "properties": {"device_name": {"type": "string"}},
    }

    def run(self, device_name: str | None = None) -> str:
        cc = _get_chromecast(device_name)
        cc.quit_app()
        return f"Stopped casting on {cc.name}."


class PauseCastTool(Tool):
    name = "pause_cast"
    description = "Pause the media currently playing on the Chromecast."
    input_schema = {"type": "object", "properties": {"device_name": {"type": "string"}}}

    def run(self, device_name: str | None = None) -> str:
        cc = _get_chromecast(device_name)
        cc.media_controller.pause()
        return "Paused."


class ResumeCastTool(Tool):
    name = "resume_cast"
    description = "Resume paused media on the Chromecast."
    input_schema = {"type": "object", "properties": {"device_name": {"type": "string"}}}

    def run(self, device_name: str | None = None) -> str:
        cc = _get_chromecast(device_name)
        cc.media_controller.play()
        return "Resumed."


class SetCastVolumeTool(Tool):
    name = "set_cast_volume"
    description = "Set the Chromecast/TV volume (0-100)."
    input_schema = {
        "type": "object",
        "properties": {
            "volume_percent": {"type": "integer"},
            "device_name": {"type": "string"},
        },
        "required": ["volume_percent"],
    }

    def run(self, volume_percent: int, device_name: str | None = None) -> str:
        cc = _get_chromecast(device_name)
        cc.set_volume(max(0, min(100, volume_percent)) / 100)
        return f"Volume set to {volume_percent}%."


class SearchYoutubeTool(Tool):
    name = "search_youtube"
    description = "Search YouTube for videos and return title, channel, and video id."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "description": "Default 5."},
        },
        "required": ["query"],
    }

    def run(self, query: str, max_results: int = 5) -> str:
        youtube = build("youtube", "v3", developerKey=config.youtube_api_key)
        response = youtube.search().list(
            q=query, part="snippet", type="video", maxResults=max_results
        ).execute()

        items = response.get("items", [])
        if not items:
            return "No videos found."
        return "\n".join(
            f"- {item['snippet']['title']} — {item['snippet']['channelTitle']} "
            f"(video_id={item['id']['videoId']})"
            for item in items
        )


class PlayYoutubeVideoTool(Tool):
    name = "play_youtube_video"
    description = (
        "Search YouTube for a video and cast it to play on the TV. Give either a search "
        "query (plays the first result) or a specific video_id from search_youtube."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "video_id": {"type": "string"},
            "device_name": {"type": "string", "description": "Defaults to CHROMECAST_NAME."},
        },
    }

    def run(self, query: str | None = None, video_id: str | None = None, device_name: str | None = None) -> str:
        from pychromecast.controllers.youtube import YouTubeController

        if not video_id:
            if not query:
                raise ValueError("Provide either query or video_id.")
            youtube = build("youtube", "v3", developerKey=config.youtube_api_key)
            response = youtube.search().list(
                q=query, part="snippet", type="video", maxResults=1
            ).execute()
            items = response.get("items", [])
            if not items:
                return f"No video found for '{query}'."
            video_id = items[0]["id"]["videoId"]
            title = items[0]["snippet"]["title"]
        else:
            title = video_id

        cc = _get_chromecast(device_name)
        yt = YouTubeController()
        cc.register_handler(yt)
        yt.play_video(video_id)
        return f"Playing '{title}' on {cc.name}."
