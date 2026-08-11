"""Short-lived cache for read-only lookup tools (weather, web search,
dictionary, ...) so asking the same or a just-repeated question doesn't
re-pay a live network call *and* a second Claude API call every time —
this is what "assimilate something new and reuse it" means for tool
results specifically, as opposed to core/memory.py's `facts` table, which
is for durable facts about the user, not the world.

In-memory only, scoped to one ToolRegistry (so one process's lifetime) —
this is a latency cache, not a permanent knowledge store, and letting it
reset on restart avoids ever serving indefinitely stale data.

Only tools that are read-only, side-effect-free, and safe to serve
slightly stale are listed here, each with a TTL matched to how fast that
kind of information actually changes. Financial/live-status tools (stock
and crypto prices, uptime checks) are deliberately excluded — a cached
answer there would be actively misleading, not just slightly out of date.
"""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("orion.tool_cache")

# tool name -> how many seconds a cached result stays valid.
CACHEABLE_TOOLS: dict[str, int] = {
    "web_search": 300,
    "fetch_webpage": 300,
    "get_weather": 1800,
    "get_sun_times": 3600,
    "wikipedia_summary": 3600,
    "convert_currency": 300,
    "define_word": 86400,
    "get_historical_weather": 86400,  # history doesn't change
    "get_news_headlines": 300,
    "get_lyrics": 86400,
    "get_upcoming_movies": 3600,
    "search_movie": 3600,
    "read_rss_feed": 300,
    "reddit_top_posts": 300,
    "get_latest_github_release": 300,
    "get_recent_github_commits": 300,
    "get_youtube_transcript": 86400,
}


class ToolResultCache:
    def __init__(self) -> None:
        self._entries: dict[tuple, tuple[float, str]] = {}

    def get(self, tool_name: str, kwargs: dict[str, Any]) -> str | None:
        if tool_name not in CACHEABLE_TOOLS:
            return None
        key = self._key(tool_name, kwargs)
        if key is None:
            return None
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, result = entry
        if time.time() >= expires_at:
            del self._entries[key]
            return None
        logger.debug("Cache hit for '%s' %r", tool_name, kwargs)
        return result

    def set(self, tool_name: str, kwargs: dict[str, Any], result: str) -> None:
        ttl = CACHEABLE_TOOLS.get(tool_name)
        if ttl is None:
            return
        key = self._key(tool_name, kwargs)
        if key is None:
            return
        self._entries[key] = (time.time() + ttl, result)

    @staticmethod
    def _key(tool_name: str, kwargs: dict[str, Any]) -> tuple | None:
        try:
            key = (tool_name, tuple(sorted(kwargs.items())))
            hash(key)  # tuple() alone doesn't check hashability of its elements
        except TypeError:
            # An unhashable argument (a list/dict param) — none of the
            # currently cacheable tools take one, but skip caching rather
            # than ever crash dispatch over it if that ever changes.
            return None
        return key
