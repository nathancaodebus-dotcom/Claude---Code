"""Open-web tools: search, fetch a page's readable text, shorten a URL,
look up the Pi's public IP. No API keys required."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from core.http import client
from tools.base import Tool

_USER_AGENT = "Mozilla/5.0 (compatible; OrionAssistant/1.0)"


def _extract_result_url(link_el) -> str:
    """.result__url's *text* is DuckDuckGo's human-readable display string
    (domain + path, e.g. 'en.wikipedia.org/wiki/Something') with no
    scheme — not the real destination URL. The element's href is a DDG
    redirect wrapper (//duckduckgo.com/l/?uddg=<url-encoded-real-url>&...),
    not a directly fetchable link either. If the model takes the display
    text and passes it straight to fetch_webpage, httpx rejects it as an
    unsupported/invalid URL — the search tool's own "url" field wasn't
    actually usable for the obvious follow-up action. Decoding the real
    URL out of the redirect wrapper's uddg parameter fixes that; falling
    back to the (still human-readable, if not fetchable) display text if
    the wrapper's shape ever changes rather than erroring."""
    if link_el is None:
        return ""
    href = link_el.get("href", "")
    if href:
        parsed = urlparse(href if "://" in href else f"https:{href}")
        query = parse_qs(parsed.query)
        if query.get("uddg"):
            return unquote(query["uddg"][0])
    return link_el.get_text(strip=True)


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
            url = _extract_result_url(link_el)
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
