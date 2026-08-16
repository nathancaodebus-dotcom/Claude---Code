"""tools/rss_reddit_tools.py's ReadRssFeedTool. Regression coverage for a
real bug found during a full-codebase audit: feedparser treats any string
with no http/https/ftp/file/feed scheme as a local filename and does a
plain open() on it -- a feed_url like '/etc/hosts' (or any local path)
would read that file's contents instead of fetching a feed."""
from __future__ import annotations

import feedparser

from tools.rss_reddit_tools import ReadRssFeedTool


def test_rejects_a_feed_url_with_no_http_scheme(monkeypatch):
    calls = []
    monkeypatch.setattr(feedparser, "parse", lambda url: calls.append(url))

    result = ReadRssFeedTool().run(feed_url="/etc/hosts")

    assert calls == []  # feedparser.parse() never even called
    assert "http://" in result or "https://" in result


def test_rejects_a_relative_path_feed_url(monkeypatch):
    calls = []
    monkeypatch.setattr(feedparser, "parse", lambda url: calls.append(url))

    ReadRssFeedTool().run(feed_url="../../etc/passwd")

    assert calls == []


def test_accepts_a_normal_http_feed_url(monkeypatch):
    class _FakeEntry(dict):
        def get(self, key, default=""):
            return dict.get(self, key, default)

    class _FakeParsed:
        entries = [_FakeEntry(title="Post", published="today", link="https://example.com/post")]

    monkeypatch.setattr(feedparser, "parse", lambda url: _FakeParsed())

    result = ReadRssFeedTool().run(feed_url="https://example.com/feed.xml")

    assert "Post" in result
