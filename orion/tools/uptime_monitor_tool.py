"""Check whether the user's own sites/services/APIs are up, with latency."""
from __future__ import annotations

import time

import httpx

from core.http import client
from tools.base import Tool


class CheckUptimeTool(Tool):
    name = "check_service_uptime"
    description = "Check whether a URL is up and how long it takes to respond."
    input_schema = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }

    def run(self, url: str) -> str:
        start = time.monotonic()
        try:
            response = client.get(url, timeout=10, follow_redirects=True)
        except httpx.RequestError as exc:
            return f"{url} is DOWN ({exc.__class__.__name__}: {exc})"

        latency_ms = (time.monotonic() - start) * 1000
        status = "UP" if response.status_code < 400 else "DOWN"
        return f"{url} is {status} (HTTP {response.status_code}, {latency_ms:.0f} ms)"


class CheckMultipleUptimeTool(Tool):
    name = "check_multiple_service_uptime"
    description = "Check up/down status and latency for several URLs at once."
    input_schema = {
        "type": "object",
        "properties": {"urls": {"type": "array", "items": {"type": "string"}}},
        "required": ["urls"],
    }

    def run(self, urls: list[str]) -> str:
        checker = CheckUptimeTool()
        return "\n".join(f"- {checker.run(url)}" for url in urls)
