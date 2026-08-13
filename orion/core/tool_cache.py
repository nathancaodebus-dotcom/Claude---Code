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


# get() only ever evicts the one key it was asked for, so an entry for a
# query that's never repeated (e.g. a one-off web_search) would otherwise
# just sit in memory forever once expired — over a long-running process
# with heavy, varied lookup traffic that's a slow, unbounded leak. Every
# _SWEEP_INTERVAL sets, set() pays a one-off O(n) pass to drop anything
# that's expired, so memory stays bounded by *live* entries, not
# all-time-ever-cached ones.
_SWEEP_INTERVAL = 200


class ToolResultCache:
    def __init__(self) -> None:
        self._entries: dict[tuple, tuple[float, str]] = {}
        self._sets_since_sweep = 0

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
            # pop(key, None) rather than del: core/agent.py now dispatches a
            # turn's independent tool calls concurrently, so two threads can
            # race to expire the same key here — del would raise KeyError for
            # whichever thread loses that race.
            self._entries.pop(key, None)
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

        self._sets_since_sweep += 1
        if self._sets_since_sweep >= _SWEEP_INTERVAL:
            self._sets_since_sweep = 0
            self._sweep_expired()

    def _sweep_expired(self) -> None:
        now = time.time()
        expired = [key for key, (expires_at, _) in self._entries.items() if now >= expires_at]
        for key in expired:
            self._entries.pop(key, None)

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
