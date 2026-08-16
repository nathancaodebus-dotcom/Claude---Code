"""Crypto signal backtesting against real historical OHLCV — the crypto
counterpart to tools/quant_signal_tools.py's stock backtester.

CoinGecko (what the rest of tools/crypto_tools.py uses) only gives daily
granularity, capped at roughly 90 days on the free tier — not enough
history for a meaningful backtest, and no hourly/minute bars at all.
Binance's public klines REST endpoint has neither limitation and needs no
API key (found while comparing Orion against freqtrade's backtesting
engine, which runs on exactly this kind of exchange-sourced OHLCV rather
than an aggregator's spot-price snapshot), so it's used here instead —
this module deliberately does NOT depend on the optional ccxt package
(see tools/exchange_tools.py for that): backtesting is core research
functionality that should work even where ccxt failed to install.
"""
from __future__ import annotations

import datetime as dt

from core.http import client
from tools.base import Tool
from tools.signal_backtest import run_signal_backtest

_BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
_DEFAULT_LOOKBACK_BARS = 500
_MAX_LOOKBACK_BARS = 1000  # Binance's own per-request cap on klines.
_VALID_INTERVALS = {"1h", "4h", "1d"}


def _fetch_binance_klines(symbol: str, quote_currency: str, interval: str, limit: int) -> list[dict]:
    pair = f"{symbol.upper()}{quote_currency.upper()}"
    response = client.get(
        _BINANCE_KLINES_URL,
        params={"symbol": pair, "interval": interval, "limit": limit},
        timeout=15,
    )
    payload = response.json()
    if not isinstance(payload, list):
        # Binance reports errors (e.g. an unknown pair) as {"code": ..., "msg": ...}
        # with a 400 status rather than an empty list.
        return []

    bars = []
    for candle in payload:
        open_time_ms = candle[0]
        bars.append(
            {
                "date": dt.datetime.fromtimestamp(open_time_ms / 1000, tz=dt.timezone.utc).isoformat(),
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]),
            }
        )
    return bars


class BacktestCryptoSignalTool(Tool):
    name = "backtest_crypto_signal"
    description = (
        "Test a candidate quantitative signal against a cryptocurrency's real historical price "
        "history (from Binance's public market data, no exchange account needed) and report its "
        "Rank IC plus naive-strategy Sharpe/Sortino/win-rate/profit-factor/max-drawdown — the "
        "crypto counterpart to backtest_quant_signal, which only covers stocks. Write the signal "
        "as Python code defining a function `signal(bars)`, where `bars` is a chronologically-"
        "ordered list of dicts, each with keys 'date', 'open', 'high', 'low', 'close', 'volume'. "
        "Return a list the same length as `bars`: the signal's value for that bar, or None where "
        "it can't be computed yet (e.g. during a lookback warm-up period). Only Python's standard "
        "library is available inside the sandbox — no pandas/numpy. Purely a backtest against "
        "historical data — like every other tool in this project, nothing here places a trade; "
        "see propose_crypto_trade for the paper-tracking workflow once a signal looks promising."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Base asset symbol, e.g. 'BTC', 'ETH', 'SOL'."},
            "quote_currency": {"type": "string", "description": "Default 'USDT'."},
            "signal_code": {
                "type": "string",
                "description": "Python source defining `def signal(bars): ...` as described above.",
            },
            "interval": {
                "type": "string",
                "enum": sorted(_VALID_INTERVALS),
                "description": "Bar size. Default '1d'. Use '1h' or '4h' for intraday signals.",
            },
            "forward_days": {
                "type": "integer",
                "description": "How many bars ahead to measure the return the signal is tested against. Default 5.",
            },
            "lookback_bars": {
                "type": "integer",
                "description": f"Number of historical bars to fetch. Default {_DEFAULT_LOOKBACK_BARS}, max {_MAX_LOOKBACK_BARS}.",
            },
        },
        "required": ["symbol", "signal_code"],
    }

    def run(
        self,
        symbol: str,
        signal_code: str,
        quote_currency: str = "USDT",
        interval: str = "1d",
        forward_days: int = 5,
        lookback_bars: int = _DEFAULT_LOOKBACK_BARS,
    ) -> str:
        if forward_days < 1:
            # Same wrap-around footgun documented in quant_signal_tools.py's
            # BacktestQuantSignalTool: a negative value doesn't raise, it
            # silently indexes from the end of `bars` and produces a
            # nonsensical but never-erroring IC.
            return f"forward_days must be a positive number of bars, got {forward_days}."
        if interval not in _VALID_INTERVALS:
            return f"interval must be one of {sorted(_VALID_INTERVALS)}, got '{interval}'."
        lookback_bars = min(lookback_bars, _MAX_LOOKBACK_BARS)

        bars = _fetch_binance_klines(symbol, quote_currency, interval, lookback_bars)
        if len(bars) < 30:
            return (
                f"Not enough price history for '{symbol.upper()}{quote_currency.upper()}' "
                f"({len(bars)} bars found) — check the symbol/quote_currency pair exists on Binance."
            )

        label = f"{symbol.upper()}/{quote_currency.upper()} ({interval})"
        return run_signal_backtest(bars, signal_code, forward_days, label=label)
