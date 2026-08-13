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
from typing import Any

import httpx

from core.store import Store
from tools.base import Tool

_USER_AGENT = "Mozilla/5.0 (compatible; OrionAssistant/1.0)"
_COINGECKO_BASE = "https://api.coingecko.com/api/v3"


def _fetch_prices(coin_ids: list[str], vs_currency: str = "usd") -> dict[str, dict[str, float]]:
    """One batched CoinGecko call for however many coins are needed, rather
    than one call per coin — used by every tool below that needs a live
    price. Returns {coin_id: {"price": ..., "change_24h_pct": ..., ...}}."""
    response = httpx.get(
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
        response = httpx.get(
            f"{_COINGECKO_BASE}/coins/{coin.lower()}/market_chart",
            params={"vs_currency": vs_currency.lower(), "days": days, "interval": "daily"},
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        payload = response.json()
        price_points = payload.get("prices")
        if not price_points:
            return f"No historical data found for '{coin}'. Use the CoinGecko coin id, e.g. 'bitcoin'."

        prices = [p[1] for p in price_points]
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
        return (
            f"Proposal #{proposal_id}: {action} {quantity} {coin} at {info['price']} USD "
            f"(~{fee_amount:.2f} USD estimated fee at {fee_pct}%) in '{portfolio}' — PENDING, not yet "
            f"applied. Ask the user to confirm or reject it (confirm_crypto_trade / reject_crypto_trade) "
            f"before treating this as done."
        )


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
        return (
            f"Proposal #{proposal_id} confirmed and applied to the portfolio "
            f"(effective price after fee: {result['effective_price_usd']:.4f} USD, "
            f"fee cost: {result['fee_amount_usd']:.2f} USD)."
        )


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
