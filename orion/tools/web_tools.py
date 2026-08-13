"""Open-web tools: search, fetch a page's readable text, shorten a URL,
look up the Pi's public IP. No API keys required."""
from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from core.http import client
from tools.base import Tool

_USER_AGENT = "Mozilla/5.0 (compatible; OrionAssistant/1.0)"


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web for a query and return the top results (title, url, snippet)."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "description": "Default 5."},
        },
        "required": ["query"],
    }

    def run(self, query: str, max_results: int = 5) -> str:
        response = client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for result in soup.select(".result")[:max_results]:
            title_el = result.select_one(".result__title")
            snippet_el = result.select_one(".result__snippet")
            link_el = result.select_one(".result__url")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            url = link_el.get_text(strip=True) if link_el else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            results.append(f"- {title} ({url})\n  {snippet}")

        return "\n".join(results) if results else "No results found."


class FetchWebpageTool(Tool):
    name = "fetch_webpage"
    description = (
        "Fetch a web page by URL and return its readable text content (for summarizing "
        "or answering questions about a specific page). Truncated to a few thousand characters."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_chars": {"type": "integer", "description": "Default 4000."},
        },
        "required": ["url"],
    }

    def run(self, url: str, max_chars: int = 4000) -> str:
        response = client.get(
            url, headers={"User-Agent": _USER_AGENT}, timeout=15, follow_redirects=True
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))
        return text[:max_chars]


class ShortenUrlTool(Tool):
    name = "shorten_url"
    description = "Shorten a long URL into a compact tinyurl.com link."
    input_schema = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }

    def run(self, url: str) -> str:
        response = client.get(
            "https://tinyurl.com/api-create.php", params={"url": url}, timeout=10
        )
        response.raise_for_status()
        return response.text.strip()


class PublicIpTool(Tool):
    name = "get_public_ip"
    description = "Get the public IP address of the machine Orion is running on."
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        response = client.get("https://api.ipify.org", params={"format": "json"}, timeout=10)
        return response.json()["ip"]
