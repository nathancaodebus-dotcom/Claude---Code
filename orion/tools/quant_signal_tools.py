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
import json

import httpx

from core.http import client
from core.store import Store
from tools.base import Tool
from tools.sandbox_tools import _docker_client, _run_in_docker, _run_in_subprocess

_TIMEOUT_S = 20
_DEFAULT_LOOKBACK_DAYS = 500
_MAX_LOOKBACK_DAYS = 1500

_HARNESS = '''
import json

def _rank(values):
    indexed = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and values[indexed[j + 1]] == values[indexed[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[indexed[k]] = avg_rank
        i = j + 1
    return ranks

def _pearson(xs, ys):
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return 0.0
    return cov / (var_x ** 0.5 * var_y ** 0.5)

def _spearman(xs, ys):
    return _pearson(_rank(xs), _rank(ys))

bars = {bars_json}
forward_days = {forward_days}

{signal_code}

try:
    signal_values = signal(bars)
except Exception as exc:
    print(json.dumps({{"error": "signal() raised: " + repr(exc)}}))
    raise SystemExit(0)

if not isinstance(signal_values, list) or len(signal_values) != len(bars):
    print(json.dumps({{"error": "signal() must return a list the same length as bars."}}))
    raise SystemExit(0)

pairs = []
for i, sig in enumerate(signal_values):
    if sig is None:
        continue
    j = i + forward_days
    if j >= len(bars):
        continue
    fwd_return = (bars[j]["close"] - bars[i]["close"]) / bars[i]["close"]
    pairs.append((float(sig), fwd_return))

if len(pairs) < 10:
    print(json.dumps({{
        "error": "Only " + str(len(pairs)) + " usable observations (need at least 10) — "
                 "signal() returned too many None values, or the lookback window is too short."
    }}))
    raise SystemExit(0)

xs = [p[0] for p in pairs]
ys = [p[1] for p in pairs]
ic = _spearman(xs, ys)
mean_sig = sum(xs) / len(xs)
std_sig = (sum((x - mean_sig) ** 2 for x in xs) / len(xs)) ** 0.5

result = {{
    "ic": ic,
    "n_observations": len(pairs),
    "signal_mean": mean_sig,
    "signal_std": std_sig,
}}

# Naive long/flat strategy metrics (Sharpe, Sortino, max drawdown, win
# rate, profit factor) -- the standard backtest report every framework
# from Backtrader to QuantConnect leads with, alongside the IC. "Naive"
# on purpose: go long whenever the signal is above its own median,
# otherwise flat, just to turn the signal into a return series worth
# reporting these on -- not a claim that this is the *right* way to
# trade the signal. Also note forward_days windows overlap (a new
# "trade" starts every day, each one still open forward_days later), so
# these returns aren't independent the way a real walk-forward backtest's
# would be -- indicative, not rigorous.
sorted_xs = sorted(xs)
mid = len(sorted_xs) // 2
median_sig = sorted_xs[mid] if len(sorted_xs) % 2 else (sorted_xs[mid - 1] + sorted_xs[mid]) / 2
trade_returns = [ret for sig, ret in pairs if sig > median_sig]

if len(trade_returns) < 5:
    result["strategy_note"] = "Too few above-median trades to compute strategy metrics."
else:
    n = len(trade_returns)
    mean_ret = sum(trade_returns) / n
    std_ret = (sum((r - mean_ret) ** 2 for r in trade_returns) / n) ** 0.5
    sharpe = (mean_ret / std_ret) if std_ret > 0 else 0.0

    downside = [r for r in trade_returns if r < 0]
    downside_std = (sum(r ** 2 for r in downside) / n) ** 0.5 if downside else 0.0
    sortino = (mean_ret / downside_std) if downside_std > 0 else 0.0

    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r < 0]
    win_rate = len(wins) / n
    if losses:
        profit_factor = sum(wins) / abs(sum(losses)) if wins else 0.0
    else:
        profit_factor = float("inf") if wins else 0.0

    equity, peak, max_dd = 1.0, 1.0, 0.0
    for r in trade_returns:
        equity *= (1 + r)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)

    result.update({{
        "n_trades": n,
        "win_rate": win_rate,
        "sharpe": sharpe,
        "sortino": sortino,
        "profit_factor": profit_factor,
        "max_drawdown": max_dd,
    }})

print(json.dumps(result))
'''


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


def _run_sandboxed(code: str, timeout_seconds: int) -> str:
    docker_client = _docker_client()
    if docker_client is not None:
        return _run_in_docker(docker_client, code, timeout_seconds)
    return _run_in_subprocess(code, timeout_seconds)


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
        lookback_days = min(lookback_days, _MAX_LOOKBACK_DAYS)
        bars = _fetch_stooq_history(ticker, lookback_days)
        if len(bars) < 30:
            return f"Not enough price history for '{ticker}' ({len(bars)} bars found) — check the ticker."

        script = _HARNESS.format(bars_json=json.dumps(bars), forward_days=forward_days, signal_code=signal_code)
        output = _run_sandboxed(script, _TIMEOUT_S)

        try:
            result = json.loads(output.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return f"Signal execution didn't produce a parseable result:\n{output[:1000]}"

        if "error" in result:
            return f"Signal error: {result['error']}"

        summary = (
            f"{ticker.upper()} | {forward_days}-day forward Rank IC: {result['ic']:.4f} "
            f"({result['n_observations']} observations over {len(bars)} bars of history) | "
            f"signal mean {result['signal_mean']:.4f}, std {result['signal_std']:.4f}"
        )

        if "strategy_note" in result:
            return f"{summary}\n{result['strategy_note']}"

        return (
            f"{summary}\n"
            f"Naive long-when-above-median strategy ({result['n_trades']} trades, overlapping "
            f"windows — indicative, not a rigorous walk-forward backtest): "
            f"win rate {result['win_rate']:.1%}, Sharpe {result['sharpe']:.2f}, "
            f"Sortino {result['sortino']:.2f}, profit factor {result['profit_factor']:.2f}, "
            f"max drawdown {result['max_drawdown']:.1%}"
        )


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
