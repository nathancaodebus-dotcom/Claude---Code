"""Custom news/discussion aggregation: arbitrary RSS feeds (feedparser) and
Reddit's public JSON endpoints (no auth needed for public subreddits)."""
from __future__ import annotations

import feedparser
import httpx

from tools.base import Tool

_USER_AGENT = "Mozilla/5.0 (compatible; OrionAssistant/1.0)"


class ReadRssFeedTool(Tool):
    name = "read_rss_feed"
    description = "Read recent entries from an RSS/Atom feed URL."
    input_schema = {
        "type": "object",
        "properties": {
            "feed_url": {"type": "string"},
            "max_results": {"type": "integer", "description": "Default 10."},
        },
        "required": ["feed_url"],
    }

    def run(self, feed_url: str, max_results: int = 10) -> str:
        parsed = feedparser.parse(feed_url)
        if not parsed.entries:
            return f"No entries found for feed '{feed_url}'."

        lines = []
        for entry in parsed.entries[:max_results]:
            published = entry.get("published", "")
            lines.append(f"- {entry.get('title', '(no title)')} ({published}) — {entry.get('link', '')}")
        return "\n".join(lines)


class RedditTopPostsTool(Tool):
    name = "reddit_top_posts"
    description = "Get top posts from a public subreddit."
    input_schema = {
        "type": "object",
        "properties": {
            "subreddit": {"type": "string", "description": "Without the 'r/' prefix, e.g. 'python'."},
            "time_range": {
                "type": "string",
                "enum": ["hour", "day", "week", "month", "year", "all"],
                "description": "Default 'day'.",
            },
            "max_results": {"type": "integer", "description": "Default 10."},
        },
        "required": ["subreddit"],
    }

    def run(self, subreddit: str, time_range: str = "day", max_results: int = 10) -> str:
        response = httpx.get(
            f"https://www.reddit.com/r/{subreddit}/top.json",
            params={"t": time_range, "limit": max_results},
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        posts = response.json()["data"]["children"]
        if not posts:
            return f"No posts found for r/{subreddit}."

        lines = []
        for post in posts:
            data = post["data"]
            lines.append(f"- {data['title']} ({data['score']} upvotes) — https://reddit.com{data['permalink']}")
        return "\n".join(lines)
