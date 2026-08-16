"""Shared sandboxed backtest harness: given a chronological list of OHLCV
bars and a Python `signal(bars)` function, scores the signal's predictive
power (Rank IC) and reports naive-strategy Sharpe/Sortino/win-rate/profit-
factor/max-drawdown.

Originally lived inline in tools/quant_signal_tools.py (stocks, via stooq).
Extracted so tools/crypto_backtest_tool.py (crypto, via Binance) can reuse
the exact same harness and report format instead of duplicating ~150 lines
of sandboxed-execution and statistics code — the harness itself has no
notion of "stock" vs. "crypto", it just operates on bars with
date/open/high/low/close/volume keys.
"""
from __future__ import annotations

import json

from tools.sandbox_tools import _docker_client, _run_in_docker, _run_in_subprocess

_TIMEOUT_S = 20

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


def _run_sandboxed(code: str, timeout_seconds: int) -> str:
    docker_client = _docker_client()
    if docker_client is not None:
        return _run_in_docker(docker_client, code, timeout_seconds)
    return _run_in_subprocess(code, timeout_seconds)


def run_signal_backtest(bars: list[dict], signal_code: str, forward_days: int, label: str) -> str:
    """Runs `signal_code` (must define `def signal(bars): ...`) against
    `bars` inside the sandbox and returns a human-readable report. `label`
    is just what's printed at the front of the report (e.g. a stock ticker
    or a crypto pair) — this function has no opinion on what kind of asset
    the bars came from."""
    script = _HARNESS.format(bars_json=json.dumps(bars), forward_days=forward_days, signal_code=signal_code)
    output = _run_sandboxed(script, _TIMEOUT_S)

    try:
        result = json.loads(output.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return f"Signal execution didn't produce a parseable result:\n{output[:1000]}"

    if "error" in result:
        return f"Signal error: {result['error']}"

    summary = (
        f"{label} | {forward_days}-day forward Rank IC: {result['ic']:.4f} "
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
