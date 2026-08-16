"""Quantitative signal research: propose a formula that scores each day of
a stock's history, test how well it actually predicted future returns
(Rank IC — Spearman correlation between the signal and the N-day-forward
return), and keep the ones worth remembering.

This is the same closed loop as NVIDIA's Quantitative Signal Discovery
Agent blueprint (generate an idea -> code it -> evaluate its Rank IC ->
keep or refine) but built on what this project already has instead of a
separate GPU/NIM stack: the "idea generation" step is just Claude
reasoning in conversation (no extra LLM call needed), historical prices
come from stooq.com (same free, keyless source tools/info_tools.py
already uses for quotes), and the signal code actually runs inside the
existing sandbox (tools/sandbox_tools.py) rather than a second, less
careful exec() path — a model-authored formula is untrusted input just
like a user-authored script is.

Pure research/backtesting only: nothing here places a trade. See
tools/crypto_tools.py for the analogous "propose, never auto-execute"
posture on the trading side of this project.
"""
from __future__ import annotations

import csv
import datetime as dt
import io

import httpx

from core.http import client
from core.store import Store
from tools.base import Tool
from tools.signal_backtest import run_signal_backtest

_DEFAULT_LOOKBACK_DAYS = 500
_MAX_LOOKBACK_DAYS = 1500


def _fetch_stooq_history(ticker: str, lookback_days: int) -> list[dict]:
    end = dt.date.today()
    start = end - dt.timedelta(days=lookback_days)
    response = client.get(
        "https://stooq.com/q/d/l/",
        params={"s": f"{ticker.lower()}.us", "d1": start.strftime("%Y%m%d"), "d2": end.strftime("%Y%m%d"), "i": "d"},
        timeout=15,
    )
    response.raise_for_status()
    text = response.text.strip()
    if not text or text.lower().startswith("no data"):
        return []

    bars = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            bars.append(
                {
                    "date": row["Date"],
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"]),
                }
            )
        except (KeyError, ValueError, TypeError):
            continue
    bars.sort(key=lambda b: b["date"])
    return bars


class BacktestQuantSignalTool(Tool):
    name = "backtest_quant_signal"
    description = (
        "Test a candidate quantitative signal against a stock's real price history and report "
        "its Rank IC (Spearman correlation between the signal's daily value and the stock's "
        "N-day-forward return) — the standard measure of a signal's predictive power. Write the "
        "signal as Python code defining a function `signal(bars)`, where `bars` is a "
        "chronologically-ordered list of dicts, each with keys 'date', 'open', 'high', 'low', "
        "'close', 'volume'. Return a list the same length as `bars`: the signal's value for that "
        "day, or None where it can't be computed yet (e.g. during a lookback warm-up period). "
        "Only Python's standard library is available inside the sandbox — no pandas/numpy — so "
        "write the formula using plain loops/math/statistics. Also reports standard backtest "
        "metrics (win rate, Sharpe, Sortino, profit factor, max drawdown) for a naive "
        "long-when-above-median strategy built from the signal, the same headline numbers "
        "Backtrader/QuantConnect-style backtests report. Reports raw numbers only; it doesn't "
        "judge what counts as 'good' — that's for Claude to reason about against what the user is "
        "actually trying to find (a rough rule of thumb: |IC| > 0.05 is considered notable in "
        "quant finance, > 0.1 quite strong, but this depends heavily on the asset and horizon)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "US stock ticker, e.g. 'AAPL', 'MSFT'."},
            "signal_code": {
                "type": "string",
                "description": "Python source defining `def signal(bars): ...` as described above.",
            },
            "forward_days": {
                "type": "integer",
                "description": "How many trading days ahead to measure the return the signal is tested against. Default 5.",
            },
            "lookback_days": {
                "type": "integer",
                "description": f"Calendar days of history to fetch. Default {_DEFAULT_LOOKBACK_DAYS}, max {_MAX_LOOKBACK_DAYS}.",
            },
        },
        "required": ["ticker", "signal_code"],
    }

    def run(
        self,
        ticker: str,
        signal_code: str,
        forward_days: int = 5,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
    ) -> str:
        if forward_days < 1:
            # The harness indexes bars[i + forward_days] to find each day's
            # forward return — with no lower-bound check, a negative value
            # doesn't raise, it silently wraps via Python's negative-index
            # semantics into bars *near the end of the whole history*
            # instead, computing a nonsensical (and never-erroring) IC
            # against unrelated bars. save_quant_signal would then happily
            # persist a signal that scored well purely because of this bug.
            return f"forward_days must be a positive number of trading days, got {forward_days}."
        lookback_days = min(lookback_days, _MAX_LOOKBACK_DAYS)
        bars = _fetch_stooq_history(ticker, lookback_days)
        if len(bars) < 30:
            return f"Not enough price history for '{ticker}' ({len(bars)} bars found) — check the ticker."

        return run_signal_backtest(bars, signal_code, forward_days, label=ticker.upper())


class SaveQuantSignalTool(Tool):
    requires_network = False
    name = "save_quant_signal"
    description = "Save a quantitative signal that backtested well, so it can be found and reused later."
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "A short memorable name, e.g. '5d momentum reversal'."},
            "ticker": {"type": "string"},
            "signal_code": {"type": "string", "description": "The same code passed to backtest_quant_signal."},
            "ic_score": {"type": "number", "description": "The Rank IC it achieved."},
            "forward_days": {"type": "integer"},
            "notes": {"type": "string", "description": "Optional context — why it works, caveats, etc."},
        },
        "required": ["name", "ticker", "signal_code", "ic_score", "forward_days"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(
        self, name: str, ticker: str, signal_code: str, ic_score: float, forward_days: int, notes: str = ""
    ) -> str:
        signal_id = self._store.save_quant_signal(name, ticker, signal_code, ic_score, forward_days, notes)
        return f"Saved signal #{signal_id} '{name}' for {ticker.upper()} (IC {ic_score:.4f})."


class ListQuantSignalsTool(Tool):
    requires_network = False
    name = "list_quant_signals"
    description = "List saved quantitative signals, best Rank IC first, optionally filtered to one ticker."
    input_schema = {
        "type": "object",
        "properties": {"ticker": {"type": "string"}},
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, ticker: str | None = None) -> str:
        signals = self._store.list_quant_signals(ticker)
        if not signals:
            return "No saved signals yet."
        return "\n".join(
            f"#{s.id} '{s.name}' [{s.ticker}] IC={s.ic_score:.4f} ({s.forward_days}d forward)"
            + (f" — {s.notes}" if s.notes else "")
            for s in signals
        )
