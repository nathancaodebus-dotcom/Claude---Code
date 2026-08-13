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
