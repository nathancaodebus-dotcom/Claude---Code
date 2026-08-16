"""Crypto research, comparison, and paper-tracked portfolio management —
the "knowledge, research, comparison" segment for crypto specifically.

Deliberately does NOT place real orders on any exchange: there's no
exchange/broker integration here at all, on purpose. Every position change
goes through propose_crypto_trade (which fetches the live price itself
rather than trusting whatever the model supplies, so a stale or
hallucinated number can't sneak into a proposal) and only actually changes
crypto_holdings once the user explicitly calls confirm_crypto_trade — see
the system prompt in core/agent.py for the instruction that keeps Claude on
this propose-then-wait path rather than assuming a proposal is done.
"""
from __future__ import annotations

import statistics
import time
from typing import Any

import httpx

from core.http import client
from core.store import Store
from tools.base import Tool

_USER_AGENT = "Mozilla/5.0 (compatible; OrionAssistant/1.0)"
_COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# How many consecutive losing confirmed sells in a portfolio trigger a
# guardrail warning on new proposals — the same idea as freqtrade's
# "protections" plugins (max_drawdown_protection, stoploss_guard), but
# implemented as a warning rather than a hard block: this is paper trading,
# so the cost of a false-positive block is real (an annoyed user) while the
# cost of a missed warning is not (no real money at risk either way).
_LOSS_STREAK_WARNING_THRESHOLD = 3


def _fetch_prices(coin_ids: list[str], vs_currency: str = "usd") -> dict[str, dict[str, float]]:
    """One batched CoinGecko call for however many coins are needed, rather
    than one call per coin — used by every tool below that needs a live
    price. Returns {coin_id: {"price": ..., "change_24h_pct": ..., ...}}."""
    response = client.get(
        f"{_COINGECKO_BASE}/simple/price",
        params={
            "ids": ",".join(sorted(set(c.lower() for c in coin_ids))),
            "vs_currencies": vs_currency.lower(),
            "include_24hr_change": "true",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
        },
        headers={"User-Agent": _USER_AGENT},
        timeout=10,
    )
    data = response.json()
    result = {}
    for coin_id, values in data.items():
        result[coin_id] = {
            "price": values.get(vs_currency.lower()),
            "change_24h_pct": values.get(f"{vs_currency.lower()}_24h_change"),
            "market_cap": values.get(f"{vs_currency.lower()}_market_cap"),
            "volume_24h": values.get(f"{vs_currency.lower()}_24h_vol"),
        }
    return result


def _sma(prices: list[float], window: int) -> float | None:
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window


def _rsi(prices: list[float], period: int = 14) -> float | None:
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    recent = deltas[-period:]
    avg_gain = sum(d for d in recent if d > 0) / period
    avg_loss = sum(-d for d in recent if d < 0) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def _volatility_pct(prices: list[float]) -> float | None:
    if len(prices) < 3:
        return None
    returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices)) if prices[i - 1]]
    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * 100


def _rolling_sma(prices: list[float], window: int) -> list[float | None]:
    """Like _sma above, but returns a value for every index instead of just
    the trailing window — used by GetCryptoTrendSignalTool to know how the
    SMA7-vs-SMA30 relationship evolved day by day, not just where it stands
    today."""
    result: list[float | None] = [None] * len(prices)
    for i in range(window - 1, len(prices)):
        result[i] = sum(prices[i - window + 1 : i + 1]) / window
    return result


def _fetch_daily_prices(coin: str, days: int, vs_currency: str = "usd") -> list[float]:
    """Shared by GetCryptoTechnicalIndicatorsTool and GetCryptoTrendSignalTool
    — both need the same daily close-price history from CoinGecko's
    market_chart endpoint, just to compute different things from it."""
    response = client.get(
        f"{_COINGECKO_BASE}/coins/{coin.lower()}/market_chart",
        params={"vs_currency": vs_currency.lower(), "days": days, "interval": "daily"},
        headers={"User-Agent": _USER_AGENT},
        timeout=10,
    )
    payload = response.json()
    price_points = payload.get("prices")
    if not price_points:
        return []
    return [p[1] for p in price_points]


class GetCryptoMarketDataTool(Tool):
    name = "get_crypto_market_data"
    description = (
        "Get a cryptocurrency's current price, 24h change %, market cap, and 24h volume — "
        "richer than get_crypto_price, for research rather than a quick price check."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "coin": {"type": "string", "description": "CoinGecko coin id, e.g. 'bitcoin', 'ethereum'."},
            "vs_currency": {"type": "string", "description": "Default 'usd'."},
        },
        "required": ["coin"],
    }

    def run(self, coin: str, vs_currency: str = "usd") -> str:
        data = _fetch_prices([coin], vs_currency)
        info = data.get(coin.lower())
        if info is None or info["price"] is None:
            return f"No data found for '{coin}'. Use the CoinGecko coin id, e.g. 'bitcoin' not 'BTC'."

        summary = f"{coin}: {info['price']} {vs_currency.upper()}"
        if info["change_24h_pct"] is not None:
            summary += f" ({info['change_24h_pct']:+.2f}% 24h)"
        if info["market_cap"]:
            summary += f", market cap {info['market_cap']:,.0f}"
        if info["volume_24h"]:
            summary += f", 24h volume {info['volume_24h']:,.0f}"
        return summary


class CompareCryptoAssetsTool(Tool):
    name = "compare_crypto_assets"
    description = "Compare several cryptocurrencies side by side: price, 24h change %, market cap, volume."
    input_schema = {
        "type": "object",
        "properties": {
            "coins": {
                "type": "array",
                "items": {"type": "string"},
                "description": "CoinGecko coin ids, e.g. ['bitcoin', 'ethereum', 'solana'].",
            },
            "vs_currency": {"type": "string", "description": "Default 'usd'."},
        },
        "required": ["coins"],
    }

    def run(self, coins: list[str], vs_currency: str = "usd") -> str:
        data = _fetch_prices(coins, vs_currency)
        lines = []
        for coin in coins:
            info = data.get(coin.lower())
            if info is None or info["price"] is None:
                lines.append(f"- {coin}: no data found")
                continue
            change = f"{info['change_24h_pct']:+.2f}%" if info["change_24h_pct"] is not None else "n/a"
            cap = f"{info['market_cap']:,.0f}" if info["market_cap"] else "n/a"
            lines.append(f"- {coin}: {info['price']} {vs_currency.upper()}, 24h {change}, cap {cap}")
        return "\n".join(lines)


class GetCryptoTechnicalIndicatorsTool(Tool):
    name = "get_crypto_technical_indicators"
    description = (
        "Get basic technical indicators for a cryptocurrency over the last N days: 7-day and "
        "30-day simple moving averages, 14-day RSI, and recent daily-return volatility. Reports "
        "raw numbers only — it doesn't decide what they mean, that's for Claude to reason about "
        "against the user's actual question."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "coin": {"type": "string", "description": "CoinGecko coin id, e.g. 'bitcoin'."},
            "days": {"type": "integer", "description": "History window in days. Default 30, max 90."},
            "vs_currency": {"type": "string", "description": "Default 'usd'."},
        },
        "required": ["coin"],
    }

    def run(self, coin: str, days: int = 30, vs_currency: str = "usd") -> str:
        days = min(days, 90)
        prices = _fetch_daily_prices(coin, days, vs_currency)
        if not prices:
            return f"No historical data found for '{coin}'. Use the CoinGecko coin id, e.g. 'bitcoin'."

        sma_7 = _sma(prices, 7)
        sma_30 = _sma(prices, 30)
        rsi_14 = _rsi(prices, 14)
        volatility = _volatility_pct(prices)

        parts = [f"{coin} over the last {days}d ({len(prices)} daily points):"]
        parts.append(f"current: {prices[-1]:.4f} {vs_currency.upper()}")
        parts.append(f"SMA7: {sma_7:.4f}" if sma_7 is not None else "SMA7: not enough history")
        parts.append(f"SMA30: {sma_30:.4f}" if sma_30 is not None else "SMA30: not enough history")
        parts.append(f"RSI14: {rsi_14:.1f}" if rsi_14 is not None else "RSI14: not enough history")
        parts.append(
            f"daily volatility (stdev of returns): {volatility:.2f}%"
            if volatility is not None
            else "volatility: not enough history"
        )
        return "\n".join(parts)


class ProposeCryptoTradeTool(Tool):
    name = "propose_crypto_trade"
    description = (
        "Propose a crypto trade (buy or sell) in a named paper portfolio (e.g. 'stable', 'risky') "
        "with your reasoning — this does NOT execute anything or change the portfolio. It fetches "
        "the current live price itself and stores a pending proposal; the user must explicitly "
        "confirm it with confirm_crypto_trade before it affects any holdings. Never tell the user "
        "a trade is done just because you proposed it. Includes an estimated trading fee (default "
        "0.1%, roughly a typical major-exchange taker fee — adjust fee_pct if the user trades "
        "somewhere with different fees) so the paper-tracked P&L doesn't look artificially better "
        "than a real account would, the same realism backtesting frameworks like Freqtrade insist on."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "portfolio": {"type": "string", "description": "e.g. 'stable' or 'risky'."},
            "action": {"type": "string", "enum": ["buy", "sell"]},
            "coin": {"type": "string", "description": "CoinGecko coin id, e.g. 'bitcoin'."},
            "quantity": {"type": "number"},
            "reasoning": {"type": "string", "description": "Why this trade, in a sentence or two."},
            "fee_pct": {
                "type": "number",
                "description": "Trading fee as a percent of trade value. Default 0.1 (0.1%).",
            },
        },
        "required": ["portfolio", "action", "coin", "quantity", "reasoning"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(
        self,
        portfolio: str,
        action: str,
        coin: str,
        quantity: float,
        reasoning: str,
        fee_pct: float = 0.1,
    ) -> str:
        prices = _fetch_prices([coin])
        info = prices.get(coin.lower())
        if info is None or info["price"] is None:
            return f"No live price found for '{coin}' — can't propose a trade without one."

        proposal_id = self._store.propose_crypto_trade(
            portfolio=portfolio,
            action=action,
            coin=coin,
            quantity=quantity,
            price_usd=info["price"],
            reasoning=reasoning,
            fee_pct=fee_pct,
        )
        fee_amount = quantity * info["price"] * (fee_pct / 100)
        result = (
            f"Proposal #{proposal_id}: {action} {quantity} {coin} at {info['price']} USD "
            f"(~{fee_amount:.2f} USD estimated fee at {fee_pct}%) in '{portfolio}' — PENDING, not yet "
            f"applied. Ask the user to confirm or reject it (confirm_crypto_trade / reject_crypto_trade) "
            f"before treating this as done."
        )

        loss_streak = self._store.recent_crypto_loss_streak(portfolio)
        if loss_streak >= _LOSS_STREAK_WARNING_THRESHOLD:
            result += (
                f"\n⚠️ Guardrail: '{portfolio}' has {loss_streak} consecutive losing confirmed sells "
                "in a row — worth flagging to the user before they confirm another trade here, not "
                "a reason to withhold the proposal on your own initiative."
            )
        return result


class ConfirmCryptoTradeTool(Tool):
    name = "confirm_crypto_trade"
    description = (
        "Apply a pending crypto trade proposal to its portfolio's holdings. Only call this after "
        "the user has explicitly agreed to the specific proposal — never on your own initiative."
    )
    input_schema = {
        "type": "object",
        "properties": {"proposal_id": {"type": "integer"}},
        "required": ["proposal_id"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, proposal_id: int) -> str:
        result = self._store.confirm_crypto_trade(proposal_id)
        message = (
            f"Proposal #{proposal_id} confirmed and applied to the portfolio "
            f"(effective price after fee: {result['effective_price_usd']:.4f} USD, "
            f"fee cost: {result['fee_amount_usd']:.2f} USD)."
        )
        if "realized_pnl_usd" in result:
            message += f" Realized P&L on this sell: {result['realized_pnl_usd']:+.2f} USD."
        return message


class SuggestPositionSizeTool(Tool):
    requires_network = False
    name = "suggest_position_size"
    description = (
        "Suggest a trade size using fixed-fractional risk management — the standard approach most "
        "trading education and frameworks (e.g. Freqtrade) default to: risk only a small, fixed "
        "percentage of the portfolio on any single trade, sized so hitting the stop-loss costs "
        "exactly that percentage, no more. Pure calculation — doesn't place, propose, or even "
        "reference a specific coin; just the math, in whatever currency/asset units are given."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "portfolio_value": {"type": "number", "description": "Total portfolio value, in your quote currency."},
            "entry_price": {"type": "number"},
            "stop_loss_price": {"type": "number", "description": "The price at which you'd exit to cap the loss."},
            "risk_pct": {
                "type": "number",
                "description": "Percent of the portfolio to risk on this one trade. Default 1 — 1-2% is the "
                "typical conservative range; going much above 2-3% on a single position is unusual "
                "even for aggressive traders.",
            },
        },
        "required": ["portfolio_value", "entry_price", "stop_loss_price"],
    }

    def run(
        self, portfolio_value: float, entry_price: float, stop_loss_price: float, risk_pct: float = 1.0
    ) -> str:
        if portfolio_value <= 0:
            return "portfolio_value must be positive."
        if entry_price <= 0 or stop_loss_price <= 0:
            return "entry_price and stop_loss_price must be positive."
        if entry_price == stop_loss_price:
            return "entry_price and stop_loss_price can't be equal — there'd be no defined risk per unit."
        if not (0 < risk_pct <= 100):
            return "risk_pct must be between 0 and 100."

        risk_amount = portfolio_value * (risk_pct / 100)
        price_risk_per_unit = abs(entry_price - stop_loss_price)
        position_size = risk_amount / price_risk_per_unit
        position_value = position_size * entry_price
        stop_distance_pct = price_risk_per_unit / entry_price * 100

        result = (
            f"Risking {risk_pct}% of {portfolio_value:,.2f} = {risk_amount:,.2f} at risk. "
            f"Stop is {stop_distance_pct:.2f}% from entry ({price_risk_per_unit:.6g} per unit). "
            f"Suggested size: {position_size:.6g} units "
            f"({position_value:,.2f} position value at entry price)."
        )
        if position_value > portfolio_value:
            result += (
                f" Note: that's {position_value / portfolio_value:.1%} of the whole portfolio in one "
                "position because the stop is very close to entry — sizing this large is risky regardless "
                "of the risk-per-trade math; consider a wider stop or a lower risk_pct."
            )
        return result


class RejectCryptoTradeTool(Tool):
    name = "reject_crypto_trade"
    description = "Discard a pending crypto trade proposal without applying it."
    input_schema = {
        "type": "object",
        "properties": {"proposal_id": {"type": "integer"}},
        "required": ["proposal_id"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, proposal_id: int) -> str:
        self._store.reject_crypto_trade(proposal_id)
        return f"Proposal #{proposal_id} rejected."


class ListPendingCryptoTradesTool(Tool):
    name = "list_pending_crypto_trades"
    description = "List crypto trade proposals still awaiting the user's confirmation or rejection."
    input_schema = {
        "type": "object",
        "properties": {"portfolio": {"type": "string", "description": "Optional filter."}},
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, portfolio: str | None = None) -> str:
        pending = self._store.list_pending_crypto_trades(portfolio)
        if not pending:
            return "No pending trade proposals."
        return "\n".join(
            f"#{p.id} [{p.portfolio}] {p.action} {p.quantity} {p.coin} @ {p.price_usd} USD — {p.reasoning}"
            for p in pending
        )


class ListCryptoHoldingsTool(Tool):
    name = "list_crypto_holdings"
    description = (
        "List current crypto holdings (optionally filtered to one portfolio) with live "
        "price and unrealized profit/loss versus the average buy price."
    )
    input_schema = {
        "type": "object",
        "properties": {"portfolio": {"type": "string", "description": "Optional filter, e.g. 'stable'."}},
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, portfolio: str | None = None) -> str:
        holdings = self._store.list_crypto_holdings(portfolio)
        if not holdings:
            return "No holdings recorded." + (f" in '{portfolio}'" if portfolio else "")

        prices = _fetch_prices([h.coin for h in holdings])
        lines = []
        for h in holdings:
            info = prices.get(h.coin)
            current_price = info["price"] if info else None
            cost_basis = h.quantity * h.avg_buy_price_usd
            if current_price is not None:
                value = h.quantity * current_price
                pnl_pct = (current_price - h.avg_buy_price_usd) / h.avg_buy_price_usd * 100
                lines.append(
                    f"- [{h.portfolio}] {h.quantity} {h.coin} @ avg {h.avg_buy_price_usd:.4f} USD "
                    f"(cost {cost_basis:.2f}) — now {current_price:.4f} USD, "
                    f"value {value:.2f} USD, P&L {pnl_pct:+.2f}%"
                )
            else:
                lines.append(
                    f"- [{h.portfolio}] {h.quantity} {h.coin} @ avg {h.avg_buy_price_usd:.4f} USD "
                    f"(cost {cost_basis:.2f}) — current price unavailable"
                )
        return "\n".join(lines)


class ScreenCryptoCandidatesTool(Tool):
    name = "screen_crypto_candidates"
    description = (
        "Screen the top coins by market cap for ones matching simple filters (minimum market cap, "
        "minimum 24h volume, 24h change % range) — the same idea as freqtrade's dynamic pairlist "
        "filters, for finding candidates worth a closer look without having to already know which "
        "coins to check. Cheap: uses the same market-cap/volume/change data compare_crypto_assets "
        "reports, just over a broader universe with filters applied."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "vs_currency": {"type": "string", "description": "Default 'usd'."},
            "top_n": {
                "type": "integer",
                "description": "How many top-by-market-cap coins to screen. Default 100, max 250.",
            },
            "min_market_cap": {"type": "number", "description": "Optional floor."},
            "min_volume_24h": {"type": "number", "description": "Optional floor."},
            "min_24h_change_pct": {"type": "number", "description": "Optional floor, e.g. 0 for 'gaining only'."},
            "max_24h_change_pct": {"type": "number", "description": "Optional ceiling, e.g. 0 for 'losing only'."},
            "max_results": {"type": "integer", "description": "Cap on how many matches to return. Default 20."},
        },
    }

    def run(
        self,
        vs_currency: str = "usd",
        top_n: int = 100,
        min_market_cap: float | None = None,
        min_volume_24h: float | None = None,
        min_24h_change_pct: float | None = None,
        max_24h_change_pct: float | None = None,
        max_results: int = 20,
    ) -> str:
        top_n = min(top_n, 250)  # CoinGecko's own per-page cap.
        response = client.get(
            f"{_COINGECKO_BASE}/coins/markets",
            params={
                "vs_currency": vs_currency.lower(),
                "order": "market_cap_desc",
                "per_page": top_n,
                "page": 1,
                "price_change_percentage": "24h",
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=15,
        )
        coins = response.json()
        if not isinstance(coins, list):
            return "CoinGecko didn't return a coin list — try again in a moment."

        matches = []
        for c in coins:
            market_cap = c.get("market_cap")
            volume = c.get("total_volume")
            change = c.get("price_change_percentage_24h")
            if min_market_cap is not None and (market_cap is None or market_cap < min_market_cap):
                continue
            if min_volume_24h is not None and (volume is None or volume < min_volume_24h):
                continue
            if min_24h_change_pct is not None and (change is None or change < min_24h_change_pct):
                continue
            if max_24h_change_pct is not None and (change is None or change > max_24h_change_pct):
                continue
            matches.append(c)

        matches = matches[:max_results]
        if not matches:
            return f"No coins in the top {top_n} by market cap matched those filters."

        lines = [
            f"- {c['id']} ({c['symbol'].upper()}): {c['current_price']} {vs_currency.upper()}, "
            f"cap {c['market_cap']:,.0f}, 24h vol {c['total_volume']:,.0f}, "
            f"24h change {c['price_change_percentage_24h']:+.2f}%"
            for c in matches
        ]
        return "\n".join(lines)


class GetCryptoTrendSignalTool(Tool):
    name = "get_crypto_trend_signal"
    description = (
        "Get a persistence-filtered SMA7/SMA30 crossover trend for a coin: bullish when SMA7 is "
        "above SMA30, bearish when below. Rather than reacting to every single crossover (which "
        "whipsaws in choppy conditions — the same noise MACD-style strategies filter out by "
        "requiring a crossed state to hold for several bars before treating it as a real trend "
        "change), this reports how many consecutive days the current state has actually persisted, "
        "and flags whether that meets the requested persistence threshold."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "coin": {"type": "string", "description": "CoinGecko coin id, e.g. 'bitcoin'."},
            "days": {"type": "integer", "description": "History window in days. Default 60, max 90."},
            "vs_currency": {"type": "string", "description": "Default 'usd'."},
            "persistence_days": {
                "type": "integer",
                "description": "Consecutive days the crossover state must hold to count as confirmed. Default 2.",
            },
        },
        "required": ["coin"],
    }

    def run(
        self, coin: str, days: int = 60, vs_currency: str = "usd", persistence_days: int = 2
    ) -> str:
        days = min(days, 90)
        prices = _fetch_daily_prices(coin, days, vs_currency)
        if not prices:
            return f"No historical data found for '{coin}'. Use the CoinGecko coin id, e.g. 'bitcoin'."

        sma7 = _rolling_sma(prices, 7)
        sma30 = _rolling_sma(prices, 30)
        states: list[str | None] = []
        for fast, slow in zip(sma7, sma30):
            if fast is None or slow is None:
                states.append(None)
            elif fast > slow:
                states.append("bullish")
            elif fast < slow:
                states.append("bearish")
            else:
                states.append("neutral")

        valid_states = [s for s in states if s is not None]
        if not valid_states:
            return f"Not enough history for '{coin}' to compute a trend (need at least 30 days)."

        current_state = valid_states[-1]
        persistence = 0
        for state in reversed(valid_states):
            if state != current_state:
                break
            persistence += 1

        confirmed = persistence >= persistence_days
        result = f"{coin}: {current_state} (SMA7 vs SMA30), persisted {persistence} day(s)"
        if confirmed:
            result += f" — confirmed (>= {persistence_days}-day persistence filter)."
        else:
            result += (
                f" — not yet confirmed (needs {persistence_days} day(s), has {persistence}); "
                "could still be noise/whipsaw rather than a real trend change."
            )
        return result


class SetCryptoExitRuleTool(Tool):
    requires_network = False
    name = "set_crypto_exit_rule"
    description = (
        "Set (or clear) a stop-loss price, take-profit price, and/or time limit on an existing "
        "crypto holding — purely an annotation Claude/check_crypto_exit_conditions can later check "
        "against the live price, it never sells anything by itself. Only fields you pass are "
        "changed; omitted fields keep whatever was set before. Pass clear=true to remove all exit "
        "rules from the holding instead (ignores the other fields)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "portfolio": {"type": "string"},
            "coin": {"type": "string", "description": "CoinGecko coin id, e.g. 'bitcoin'."},
            "stop_loss_price": {"type": "number", "description": "Sell-signal price if it drops this low."},
            "take_profit_price": {"type": "number", "description": "Sell-signal price if it rises this high."},
            "time_limit_hours": {
                "type": "number",
                "description": "Flag the position for review after this many hours from now.",
            },
            "clear": {"type": "boolean", "description": "If true, removes all exit rules instead. Default false."},
        },
        "required": ["portfolio", "coin"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(
        self,
        portfolio: str,
        coin: str,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        time_limit_hours: float | None = None,
        clear: bool = False,
    ) -> str:
        if clear:
            cleared = self._store.clear_crypto_exit_rule(portfolio, coin)
            if not cleared:
                return f"No holding found for '{coin}' in '{portfolio}'."
            return f"Cleared exit rules for {coin} in '{portfolio}'."

        if stop_loss_price is None and take_profit_price is None and time_limit_hours is None:
            return (
                "Nothing to set — provide at least one of stop_loss_price, take_profit_price, or "
                "time_limit_hours (or clear=true to remove existing rules)."
            )

        exit_time_limit_at = time.time() + time_limit_hours * 3600 if time_limit_hours is not None else None
        ok = self._store.set_crypto_exit_rule(
            portfolio, coin, stop_loss_price, take_profit_price, exit_time_limit_at
        )
        if not ok:
            return f"No holding found for '{coin}' in '{portfolio}' — exit rules apply to an existing position only."

        parts = []
        if stop_loss_price is not None:
            parts.append(f"stop-loss {stop_loss_price}")
        if take_profit_price is not None:
            parts.append(f"take-profit {take_profit_price}")
        if time_limit_hours is not None:
            parts.append(f"time limit in {time_limit_hours}h")
        return f"Set {', '.join(parts)} for {coin} in '{portfolio}'. Check with check_crypto_exit_conditions."


class CheckCryptoExitConditionsTool(Tool):
    name = "check_crypto_exit_conditions"
    description = (
        "Check every holding's exit rules (set via set_crypto_exit_rule) against live prices and "
        "report which have hit their stop-loss, take-profit, or time limit. Purely informational — "
        "nothing here sells anything; if a condition is flagged, propose a sell with "
        "propose_crypto_trade and let the user confirm it."
    )
    input_schema = {
        "type": "object",
        "properties": {"portfolio": {"type": "string", "description": "Optional filter."}},
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, portfolio: str | None = None) -> str:
        holdings = self._store.list_crypto_holdings(portfolio)
        watched = [
            h for h in holdings
            if h.stop_loss_price is not None or h.take_profit_price is not None or h.exit_time_limit_at is not None
        ]
        if not watched:
            return "No holdings have exit rules set." + (f" in '{portfolio}'" if portfolio else "")

        prices = _fetch_prices([h.coin for h in watched])
        now = time.time()
        triggered, clear = [], []
        for h in watched:
            info = prices.get(h.coin)
            current_price = info["price"] if info else None
            hits = []
            if current_price is not None and h.stop_loss_price is not None and current_price <= h.stop_loss_price:
                hits.append(f"STOP-LOSS hit ({current_price} <= {h.stop_loss_price})")
            if current_price is not None and h.take_profit_price is not None and current_price >= h.take_profit_price:
                hits.append(f"TAKE-PROFIT hit ({current_price} >= {h.take_profit_price})")
            if h.exit_time_limit_at is not None and now >= h.exit_time_limit_at:
                hits.append("TIME LIMIT expired")
            if hits:
                triggered.append(f"- [{h.portfolio}] {h.coin}: {'; '.join(hits)}")
            else:
                clear.append(f"- [{h.portfolio}] {h.coin}: no condition triggered")

        lines = []
        if triggered:
            lines.append("Triggered:")
            lines.extend(triggered)
        if clear:
            lines.append("Not triggered:")
            lines.extend(clear)
        return "\n".join(lines)


class GetCryptoLossStreakStatusTool(Tool):
    requires_network = False
    name = "get_crypto_loss_streak_status"
    description = (
        "Check how many consecutive losing confirmed sells a paper portfolio currently has in a "
        "row — the same status propose_crypto_trade warns about automatically once it crosses the "
        f"guardrail threshold ({_LOSS_STREAK_WARNING_THRESHOLD}), available on demand."
    )
    input_schema = {
        "type": "object",
        "properties": {"portfolio": {"type": "string"}},
        "required": ["portfolio"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, portfolio: str) -> str:
        streak = self._store.recent_crypto_loss_streak(portfolio)
        if streak == 0:
            return f"'{portfolio}' has no active losing streak (last confirmed sell, if any, wasn't a loss)."
        message = f"'{portfolio}' has {streak} consecutive losing confirmed sell(s) in a row."
        if streak >= _LOSS_STREAK_WARNING_THRESHOLD:
            message += " Guardrail threshold reached — worth flagging to the user."
        return message


class SuggestPortfolioRebalanceTool(Tool):
    name = "suggest_portfolio_rebalance"
    description = (
        "Compare a portfolio's current allocation (by live value) against target percentages per "
        "coin and report the drift — e.g. 'bitcoin is 65% but your target is 50%, overweight by "
        "15pp'. Pure calculation reported for the user's information; propose_crypto_trade is still "
        "how any actual rebalancing trade gets proposed and confirmed."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "portfolio": {"type": "string"},
            "target_allocations": {
                "type": "object",
                "description": "Map of coin id to target percent of the portfolio, e.g. {'bitcoin': 50, 'ethereum': 30, 'solana': 20}. Should sum to ~100.",
            },
        },
        "required": ["portfolio", "target_allocations"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, portfolio: str, target_allocations: dict[str, float]) -> str:
        target_total = sum(target_allocations.values())
        if target_total <= 0:
            return "target_allocations must sum to a positive number."

        holdings = self._store.list_crypto_holdings(portfolio)
        if not holdings:
            return f"No holdings recorded in '{portfolio}'."

        prices = _fetch_prices([h.coin for h in holdings])
        values: dict[str, float] = {}
        total_value = 0.0
        for h in holdings:
            info = prices.get(h.coin)
            if info is None or info["price"] is None:
                continue
            value = h.quantity * info["price"]
            values[h.coin] = value
            total_value += value

        if total_value <= 0:
            return f"Couldn't price any holdings in '{portfolio}' — can't compute allocation."

        all_coins = sorted(set(values) | set(c.lower() for c in target_allocations))
        normalized_targets = {c.lower(): p / target_total * 100 for c, p in target_allocations.items()}

        lines = [f"Total portfolio value: {total_value:.2f} USD"]
        for coin in all_coins:
            current_value = values.get(coin, 0.0)
            current_pct = current_value / total_value * 100
            target_pct = normalized_targets.get(coin, 0.0)
            drift_pp = current_pct - target_pct
            drift_value = drift_pp / 100 * total_value
            if abs(drift_pp) < 0.5:
                lines.append(f"- {coin}: {current_pct:.1f}% vs target {target_pct:.1f}% — on target")
            elif drift_pp > 0:
                lines.append(
                    f"- {coin}: {current_pct:.1f}% vs target {target_pct:.1f}% — "
                    f"overweight by {drift_pp:.1f}pp (~{drift_value:.2f} USD too much)"
                )
            else:
                lines.append(
                    f"- {coin}: {current_pct:.1f}% vs target {target_pct:.1f}% — "
                    f"underweight by {-drift_pp:.1f}pp (~{-drift_value:.2f} USD short)"
                )
        return "\n".join(lines)
