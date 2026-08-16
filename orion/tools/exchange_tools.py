"""Read-only market data straight from exchanges, via ccxt — order book
depth and cross-exchange price comparison, neither of which CoinGecko (what
the rest of tools/crypto_tools.py uses) can provide: it has no order-book
data at all, and its single aggregated price can't show how much a coin's
price actually differs venue to venue right now.

Deliberately public-endpoint only: every call below works with a bare
`ccxt.<exchange>()` instance, no API key. ccxt makes authenticated trading
endpoints (create_order, fetch_balance, withdraw...) just as easy to reach,
which is exactly why this module never touches them — see
tools/crypto_tools.py's module docstring for why Orion has no real-money
execution anywhere, on purpose.

ccxt is an optional dependency (see requirements.txt) — this module is only
ever imported behind tools/registry_builder.py's _register_safe, same as
every other optional integration, so a platform where it fails to install
(e.g. Termux) just loses this one feature rather than crashing the registry.
"""
from __future__ import annotations

import ccxt

from tools.base import Tool

# A small, curated subset of ccxt's 100+ supported exchanges rather than
# allowing any of them: these are major, liquid, well-maintained venues
# whose public endpoints are reliable and don't need region-specific setup.
# Validated against ccxt.exchanges at import time so a future ccxt release
# dropping one of these loudly breaks a test instead of silently 404ing.
_SUPPORTED_EXCHANGES = ("binance", "kraken", "coinbase", "bitstamp", "okx")
assert set(_SUPPORTED_EXCHANGES).issubset(ccxt.exchanges), "ccxt dropped a supported exchange id"

_TIMEOUT_MS = 15_000


def _make_exchange(exchange_id: str):
    exchange_class = getattr(ccxt, exchange_id)
    return exchange_class({"enableRateLimit": True, "timeout": _TIMEOUT_MS})


class GetCryptoOrderBookTool(Tool):
    name = "get_crypto_order_book_depth"
    description = (
        "Get real order book depth (live bids/asks with size) for a crypto trading pair from a "
        "real exchange — CoinGecko (used by the other crypto tools) has no order-book data at "
        "all. Useful for gauging how liquid/thin a market currently is, e.g. before proposing a "
        "paper trade size with propose_crypto_trade."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Base asset, e.g. 'BTC', 'ETH'."},
            "quote_currency": {"type": "string", "description": "Default 'USDT'."},
            "exchange": {
                "type": "string",
                "enum": list(_SUPPORTED_EXCHANGES),
                "description": "Default 'binance'.",
            },
            "depth": {"type": "integer", "description": "Levels per side to report. Default 10."},
        },
        "required": ["symbol"],
    }

    def run(
        self, symbol: str, quote_currency: str = "USDT", exchange: str = "binance", depth: int = 10
    ) -> str:
        if exchange not in _SUPPORTED_EXCHANGES:
            return f"exchange must be one of {list(_SUPPORTED_EXCHANGES)}, got '{exchange}'."
        pair = f"{symbol.upper()}/{quote_currency.upper()}"
        try:
            order_book = _make_exchange(exchange).fetch_order_book(pair, limit=depth)
        except ccxt.BaseError as exc:
            return f"Couldn't fetch the order book for {pair} on {exchange}: {exc}"

        bids = order_book["bids"][:depth]
        asks = order_book["asks"][:depth]
        if not bids or not asks:
            return f"No order book data for {pair} on {exchange}."

        best_bid, best_ask = bids[0][0], asks[0][0]
        spread_pct = (best_ask - best_bid) / best_ask * 100
        bid_depth = sum(size for _, size in bids)
        ask_depth = sum(size for _, size in asks)

        return (
            f"{pair} on {exchange} — best bid {best_bid:g}, best ask {best_ask:g} "
            f"(spread {spread_pct:.3f}%). Top {len(bids)} levels: "
            f"{bid_depth:.4f} {symbol.upper()} of bid depth, {ask_depth:.4f} {symbol.upper()} of ask depth."
        )


class CompareCryptoPriceAcrossExchangesTool(Tool):
    name = "compare_crypto_price_across_exchanges"
    description = (
        "Compare a coin's current price across several real exchanges at once — CoinGecko (used "
        "by compare_crypto_assets) only has one aggregated price, so it can't show venue-to-venue "
        "divergence. Useful for spotting an unusually large spread between exchanges."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Base asset, e.g. 'BTC', 'ETH'."},
            "quote_currency": {"type": "string", "description": "Default 'USDT'."},
            "exchanges": {
                "type": "array",
                "items": {"type": "string", "enum": list(_SUPPORTED_EXCHANGES)},
                "description": f"Default all of {list(_SUPPORTED_EXCHANGES)}.",
            },
        },
        "required": ["symbol"],
    }

    def run(
        self, symbol: str, quote_currency: str = "USDT", exchanges: list[str] | None = None
    ) -> str:
        exchanges = exchanges or list(_SUPPORTED_EXCHANGES)
        unknown = [e for e in exchanges if e not in _SUPPORTED_EXCHANGES]
        if unknown:
            return f"Unknown exchange(s) {unknown} — must be from {list(_SUPPORTED_EXCHANGES)}."

        pair = f"{symbol.upper()}/{quote_currency.upper()}"
        prices: dict[str, float] = {}
        lines = []
        for exchange_id in exchanges:
            try:
                ticker = _make_exchange(exchange_id).fetch_ticker(pair)
                last = ticker.get("last")
            except ccxt.BaseError as exc:
                lines.append(f"- {exchange_id}: unavailable ({exc})")
                continue
            if last is None:
                lines.append(f"- {exchange_id}: no price reported")
                continue
            prices[exchange_id] = last
            lines.append(f"- {exchange_id}: {last:g} {quote_currency.upper()}")

        if len(prices) < 2:
            return f"{pair}:\n" + "\n".join(lines) + "\nNot enough exchanges reported a price to compare spread."

        lowest = min(prices.values())
        highest = max(prices.values())
        spread_pct = (highest - lowest) / lowest * 100
        return f"{pair}:\n" + "\n".join(lines) + f"\nSpread across exchanges: {spread_pct:.3f}%"
