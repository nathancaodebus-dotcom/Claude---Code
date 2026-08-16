"""Shared, connection-pooled HTTP client for every tool that talks to an
external API.

httpx's module-level convenience functions (httpx.get, httpx.post, ...) each
open a brand new connection — a full TCP handshake, then a TLS handshake for
every https:// call — and tear it back down again once the response is
read; that's by design, not a bug, since there's no client object around to
keep a connection on. With ~20 tool files and several dozen call sites, many
hitting the same host repeatedly across a session (Microsoft Graph, Shopify,
CoinGecko, GitHub's API, ...), that's a real and entirely avoidable cost —
tens of milliseconds of handshake paid again on every single call instead of
once per host.

One shared, persistent httpx.Client keeps a connection pool alive across
calls instead, so a repeat call to a host already used this process reuses
an existing connection. Tools import `client` from here and call
client.get/post/put/patch/delete(...) exactly like the httpx module-level
functions — same signature, same exceptions (httpx.HTTPStatusError,
httpx.RequestError, ...), just pooled.

core/offline_agent.py deliberately keeps using plain httpx.get/post instead
of this client: it only ever talks to a local Ollama server on localhost,
where there's no real handshake cost to amortize, and one of its two calls
(is_ollama_reachable) is a one-off liveness probe that's arguably clearer
as an independent request anyway.
"""
from __future__ import annotations

import atexit
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

# Limits are generous relative to what a single personal-assistant process
# actually generates (bursty, low-volume, a handful of distinct hosts) —
# there's no benefit to holding open more idle connections than that ever
# needs. 10s matches the explicit timeout= several call sites were already
# passing by hand; it's still just a default; any call can override it
# per-request (client.get(url, timeout=...)) exactly as before.
client = httpx.Client(
    timeout=10.0,
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
)
# Never explicitly closed otherwise — every interface here is a long-running
# process (a chat loop, a bot, a web server) with no single natural place to
# call client.close(), so pooled sockets would otherwise just be left open
# until the OS reclaims them at process exit. Not incorrect, just not clean;
# atexit makes sure they're actually released as part of a normal shutdown.
atexit.register(client.close)


class UnsafeUrlError(ValueError):
    """Raised by require_public_http_url() for a URL a tool shouldn't fetch."""


def require_public_http_url(url: str) -> None:
    """SSRF guard for tools that fetch a fully model/user-suppliable URL and
    return its content to the model (tools/web_tools.py's fetch_webpage is
    the motivating case, found during a full-codebase audit: nothing
    stopped a prompt-injected page or a jailbroken request from pointing it
    at http://169.254.169.254/... — a cloud metadata endpoint — or an
    internal LAN admin panel, with the full response handed back to Claude
    either way). Raises UnsafeUrlError with a human-readable reason instead
    of returning a bool, so callers can surface *why* a URL was refused.

    Deliberately not applied to every URL-fetching tool: some (uptime
    monitoring, RSS feeds) have a legitimate reason to reach a
    self-hosted/LAN service, which this would break. Scoped to the tool
    whose entire job is "return this page's content to the model."

    Best-effort, not a hardened defense: checks the scheme and the
    hostname's *currently* resolved address(es), which blocks a URL that
    directly names a private/loopback/link-local target. Two gaps this
    doesn't close: DNS rebinding (a hostname whose DNS record changes
    between this check and the actual connection), and a redirect chain
    that starts at a public URL but hops to a private one (fetch_webpage
    calls this once, up front, then still fetches with
    follow_redirects=True) — both would need a custom httpx transport with
    connection-time IP pinning on every hop to close fully."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"Unsupported URL scheme '{parsed.scheme or '(none)'}' — only http/https are allowed.")
    if not parsed.hostname:
        raise UnsafeUrlError("URL has no hostname.")
    try:
        addr_info = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Couldn't resolve '{parsed.hostname}': {exc}") from exc
    for *_rest, sockaddr in addr_info:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UnsafeUrlError(
                f"'{parsed.hostname}' resolves to a private/internal address ({ip}) — refusing to fetch it."
            )
