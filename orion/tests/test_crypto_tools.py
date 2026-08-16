import time

import httpx
import pytest

from core.store import Store
from tools.crypto_tools import (
    CheckCryptoExitConditionsTool,
    CompareCryptoAssetsTool,
    ConfirmCryptoTradeTool,
    GetCryptoLossStreakStatusTool,
    GetCryptoMarketDataTool,
    GetCryptoTechnicalIndicatorsTool,
    GetCryptoTrendSignalTool,
    ListCryptoHoldingsTool,
    ListPendingCryptoTradesTool,
    ProposeCryptoTradeTool,
    RejectCryptoTradeTool,
    ScreenCryptoCandidatesTool,
    SetCryptoExitRuleTool,
    SuggestPortfolioRebalanceTool,
    SuggestPositionSizeTool,
    _LOSS_STREAK_WARNING_THRESHOLD,
    _rolling_sma,
    _rsi,
    _sma,
    _volatility_pct,
)


class _FakeResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def json(self):
        return self._json_data


# --- pure indicator math, no mocking needed ---

def test_sma_returns_none_without_enough_history():
    assert _sma([1.0, 2.0], window=7) is None


def test_sma_averages_the_last_window():
    assert _sma([1.0, 2.0, 3.0, 100.0, 200.0, 300.0], window=3) == pytest.approx(200.0)


def test_rsi_returns_none_without_enough_history():
    assert _rsi([1.0, 2.0], period=14) is None


def test_rsi_is_100_when_every_move_is_a_gain():
    prices = [float(i) for i in range(1, 20)]  # strictly increasing
    assert _rsi(prices, period=14) == 100.0


def test_rsi_is_low_when_every_move_is_a_loss():
    prices = [float(i) for i in range(20, 1, -1)]  # strictly decreasing
    assert _rsi(prices, period=14) == 0.0


def test_volatility_is_zero_for_a_flat_price():
    assert _volatility_pct([100.0] * 10) == 0.0


def test_volatility_none_without_enough_points():
    assert _volatility_pct([100.0, 101.0]) is None


# --- tools that fetch price data (httpx.get mocked) ---

def _mock_price_response(monkeypatch, data: dict):
    monkeypatch.setattr(
        "tools.crypto_tools.client.get", lambda *a, **kw: _FakeResponse(data)
    )


def test_get_market_data_reports_full_details(monkeypatch):
    _mock_price_response(
        monkeypatch,
        {"bitcoin": {"usd": 50000, "usd_24h_change": 2.5, "usd_market_cap": 900_000_000_000, "usd_24h_vol": 3_000_000_000}},
    )
    result = GetCryptoMarketDataTool().run(coin="bitcoin")
    assert "50000" in result
    assert "+2.50%" in result
    assert "900,000,000,000" in result


def test_get_market_data_handles_unknown_coin(monkeypatch):
    _mock_price_response(monkeypatch, {})
    result = GetCryptoMarketDataTool().run(coin="not-a-coin")
    assert "No data found" in result


def test_compare_crypto_assets_lists_each_coin(monkeypatch):
    _mock_price_response(
        monkeypatch,
        {
            "bitcoin": {"usd": 50000, "usd_24h_change": 1.0, "usd_market_cap": 1, "usd_24h_vol": 1},
            "ethereum": {"usd": 3000, "usd_24h_change": -2.0, "usd_market_cap": 1, "usd_24h_vol": 1},
        },
    )
    result = CompareCryptoAssetsTool().run(coins=["bitcoin", "ethereum"])
    assert "bitcoin" in result and "50000" in result
    assert "ethereum" in result and "3000" in result


def test_technical_indicators_reports_computed_values(monkeypatch):
    prices = [[i, 100.0 + i] for i in range(30)]  # steadily rising
    monkeypatch.setattr(
        "tools.crypto_tools.client.get", lambda *a, **kw: _FakeResponse({"prices": prices})
    )
    result = GetCryptoTechnicalIndicatorsTool().run(coin="bitcoin", days=30)
    assert "SMA7" in result
    assert "SMA30" in result
    assert "RSI14" in result


def test_technical_indicators_handles_missing_coin(monkeypatch):
    monkeypatch.setattr(
        "tools.crypto_tools.client.get", lambda *a, **kw: _FakeResponse({"prices": []})
    )
    result = GetCryptoTechnicalIndicatorsTool().run(coin="not-a-coin")
    assert "No historical data" in result


# --- propose/confirm/reject workflow ---

def test_propose_crypto_trade_uses_the_live_fetched_price_not_a_model_supplied_one(monkeypatch, tmp_path):
    """input_schema has no price field at all, but this locks in the actual
    behavior: the proposal's stored price always comes from _fetch_prices."""
    _mock_price_response(monkeypatch, {"bitcoin": {"usd": 61234, "usd_24h_change": 0, "usd_market_cap": 0, "usd_24h_vol": 0}})
    store = Store(db_path=str(tmp_path / "test.db"))
    tool = ProposeCryptoTradeTool(store)

    result = tool.run(portfolio="risky", action="buy", coin="bitcoin", quantity=0.1, reasoning="momentum")

    assert "PENDING" in result
    proposal = store.list_pending_crypto_trades("risky")[0]
    assert proposal.price_usd == 61234


def test_propose_crypto_trade_fails_cleanly_without_a_live_price(monkeypatch, tmp_path):
    _mock_price_response(monkeypatch, {})
    store = Store(db_path=str(tmp_path / "test.db"))
    tool = ProposeCryptoTradeTool(store)

    result = tool.run(portfolio="risky", action="buy", coin="not-a-coin", quantity=1, reasoning="x")

    assert "No live price found" in result
    assert store.list_pending_crypto_trades("risky") == []


def test_propose_crypto_trade_reports_the_estimated_fee(monkeypatch, tmp_path):
    _mock_price_response(monkeypatch, {"bitcoin": {"usd": 100, "usd_24h_change": 0, "usd_market_cap": 0, "usd_24h_vol": 0}})
    store = Store(db_path=str(tmp_path / "test.db"))
    tool = ProposeCryptoTradeTool(store)

    result = tool.run(portfolio="risky", action="buy", coin="bitcoin", quantity=2, reasoning="x", fee_pct=0.5)

    assert "1.00 USD estimated fee at 0.5%" in result  # 2 * 100 * 0.5%
    proposal = store.list_pending_crypto_trades("risky")[0]
    assert proposal.fee_pct == 0.5


def test_confirm_and_reject_tools_delegate_to_the_store(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    proposal_id = store.propose_crypto_trade(
        portfolio="stable", action="buy", coin="bitcoin", quantity=1, price_usd=100, reasoning="x"
    )

    result = ConfirmCryptoTradeTool(store).run(proposal_id=proposal_id)

    assert "confirmed" in result
    assert "fee cost" in result
    assert store.list_crypto_holdings("stable")[0].coin == "bitcoin"


def test_reject_tool_does_not_touch_holdings(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    proposal_id = store.propose_crypto_trade(
        portfolio="stable", action="buy", coin="bitcoin", quantity=1, price_usd=100, reasoning="x"
    )

    result = RejectCryptoTradeTool(store).run(proposal_id=proposal_id)

    assert "rejected" in result
    assert store.list_crypto_holdings("stable") == []


def test_list_pending_trades_tool_reports_none_when_empty(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    assert "No pending" in ListPendingCryptoTradesTool(store).run()


def test_list_holdings_tool_reports_live_pnl(monkeypatch, tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    proposal_id = store.propose_crypto_trade(
        portfolio="stable", action="buy", coin="bitcoin", quantity=1, price_usd=100, reasoning="x"
    )
    store.confirm_crypto_trade(proposal_id)
    _mock_price_response(monkeypatch, {"bitcoin": {"usd": 150, "usd_24h_change": 0, "usd_market_cap": 0, "usd_24h_vol": 0}})

    result = ListCryptoHoldingsTool(store).run(portfolio="stable")

    assert "bitcoin" in result
    assert "+50.00%" in result  # (150 - 100) / 100 * 100


# --- suggest_position_size (pure calculation, no mocking needed) ---

def test_suggest_position_size_computes_fixed_fractional_sizing():
    result = SuggestPositionSizeTool().run(
        portfolio_value=10_000, entry_price=100, stop_loss_price=90, risk_pct=1
    )
    # risk_amount = 100, price_risk_per_unit = 10 -> position_size = 10 units, value = 1000
    assert "100.00 at risk" in result
    assert "Suggested size: 10" in result
    assert "1,000.00 position value" in result


def test_suggest_position_size_uses_default_risk_pct_of_one_percent():
    result = SuggestPositionSizeTool().run(portfolio_value=10_000, entry_price=100, stop_loss_price=95)
    assert "Risking 1.0%" in result


def test_suggest_position_size_warns_when_position_exceeds_portfolio():
    # Stop is 1% away from entry but risk_pct is 50% -> position value dwarfs the portfolio.
    result = SuggestPositionSizeTool().run(
        portfolio_value=1000, entry_price=100, stop_loss_price=99, risk_pct=50
    )
    assert "Note:" in result
    assert "of the whole portfolio in one position" in result


def test_suggest_position_size_rejects_non_positive_portfolio_value():
    assert "portfolio_value must be positive" in SuggestPositionSizeTool().run(
        portfolio_value=0, entry_price=100, stop_loss_price=90
    )


def test_suggest_position_size_rejects_non_positive_prices():
    assert "must be positive" in SuggestPositionSizeTool().run(
        portfolio_value=1000, entry_price=0, stop_loss_price=90
    )
    assert "must be positive" in SuggestPositionSizeTool().run(
        portfolio_value=1000, entry_price=100, stop_loss_price=-5
    )


def test_suggest_position_size_rejects_equal_entry_and_stop():
    result = SuggestPositionSizeTool().run(portfolio_value=1000, entry_price=100, stop_loss_price=100)
    assert "can't be equal" in result


def test_suggest_position_size_rejects_out_of_range_risk_pct():
    assert "risk_pct must be between" in SuggestPositionSizeTool().run(
        portfolio_value=1000, entry_price=100, stop_loss_price=90, risk_pct=0
    )
    assert "risk_pct must be between" in SuggestPositionSizeTool().run(
        portfolio_value=1000, entry_price=100, stop_loss_price=90, risk_pct=150
    )


# --- screen_crypto_candidates ---


def _mock_markets_response(monkeypatch, coins: list[dict]):
    monkeypatch.setattr(
        "tools.crypto_tools.client.get", lambda *a, **kw: _FakeResponse(coins)
    )


def _market_coin(id_, market_cap, volume, change):
    return {
        "id": id_,
        "symbol": id_[:3],
        "current_price": 1.0,
        "market_cap": market_cap,
        "total_volume": volume,
        "price_change_percentage_24h": change,
    }


def test_screen_crypto_candidates_filters_by_market_cap(monkeypatch):
    _mock_markets_response(
        monkeypatch,
        [_market_coin("big", 1_000_000, 1000, 1.0), _market_coin("small", 100, 1000, 1.0)],
    )
    result = ScreenCryptoCandidatesTool().run(min_market_cap=10_000)
    assert "big" in result
    assert "small" not in result


def test_screen_crypto_candidates_filters_by_change_range(monkeypatch):
    _mock_markets_response(
        monkeypatch,
        [_market_coin("gainer", 1000, 1000, 5.0), _market_coin("loser", 1000, 1000, -5.0)],
    )
    result = ScreenCryptoCandidatesTool().run(min_24h_change_pct=0)
    assert "gainer" in result
    assert "loser" not in result


def test_screen_crypto_candidates_no_matches_message(monkeypatch):
    _mock_markets_response(monkeypatch, [_market_coin("small", 100, 100, 0.0)])
    result = ScreenCryptoCandidatesTool().run(min_market_cap=999_999_999)
    assert "No coins" in result


def test_screen_crypto_candidates_caps_top_n_at_250(monkeypatch):
    captured = {}

    def fake_get(*a, **kw):
        captured["per_page"] = kw["params"]["per_page"]
        return _FakeResponse([])

    monkeypatch.setattr("tools.crypto_tools.client.get", fake_get)
    ScreenCryptoCandidatesTool().run(top_n=10_000)
    assert captured["per_page"] == 250


# --- get_crypto_trend_signal ---


def test_rolling_sma_matches_plain_sma_at_the_end():
    prices = [1.0, 2.0, 3.0, 100.0, 200.0, 300.0]
    rolling = _rolling_sma(prices, 3)
    assert rolling[-1] == pytest.approx(200.0)
    assert rolling[0] is None
    assert rolling[1] is None


def _rising_then_falling_prices(n_rising, n_falling, start=100.0):
    prices = [start + i for i in range(n_rising)]
    peak = prices[-1]
    prices += [peak - i for i in range(1, n_falling + 1)]
    return prices


def test_trend_signal_reports_bullish_for_a_steadily_rising_series(monkeypatch):
    prices = [[i, 100.0 + i] for i in range(40)]  # steadily rising -> SMA7 > SMA30 near the end
    monkeypatch.setattr(
        "tools.crypto_tools.client.get", lambda *a, **kw: _FakeResponse({"prices": prices})
    )
    result = GetCryptoTrendSignalTool().run(coin="bitcoin", days=40, persistence_days=2)
    assert "bullish" in result
    assert "confirmed" in result


def test_trend_signal_not_yet_confirmed_when_persistence_too_short(monkeypatch):
    prices = [[i, 100.0 + i] for i in range(40)]
    monkeypatch.setattr(
        "tools.crypto_tools.client.get", lambda *a, **kw: _FakeResponse({"prices": prices})
    )
    result = GetCryptoTrendSignalTool().run(coin="bitcoin", days=40, persistence_days=1000)
    assert "not yet confirmed" in result


def test_trend_signal_handles_missing_coin(monkeypatch):
    monkeypatch.setattr(
        "tools.crypto_tools.client.get", lambda *a, **kw: _FakeResponse({"prices": []})
    )
    result = GetCryptoTrendSignalTool().run(coin="not-a-coin")
    assert "No historical data" in result


def test_trend_signal_handles_not_enough_history_for_sma30(monkeypatch):
    prices = [[i, 100.0 + i] for i in range(10)]
    monkeypatch.setattr(
        "tools.crypto_tools.client.get", lambda *a, **kw: _FakeResponse({"prices": prices})
    )
    result = GetCryptoTrendSignalTool().run(coin="bitcoin", days=10)
    assert "Not enough history" in result


# --- exit rules: set_crypto_exit_rule / check_crypto_exit_conditions ---


def _confirmed_holding(tmp_path, price=100.0):
    store = Store(db_path=str(tmp_path / "test.db"))
    proposal_id = store.propose_crypto_trade(
        portfolio="stable", action="buy", coin="bitcoin", quantity=1, price_usd=price, reasoning="x"
    )
    store.confirm_crypto_trade(proposal_id)
    return store


def test_set_exit_rule_rejects_when_no_holding_exists(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    result = SetCryptoExitRuleTool(store).run(portfolio="stable", coin="bitcoin", stop_loss_price=90)
    assert "No holding found" in result


def test_set_exit_rule_requires_at_least_one_field(tmp_path):
    store = _confirmed_holding(tmp_path)
    result = SetCryptoExitRuleTool(store).run(portfolio="stable", coin="bitcoin")
    assert "Nothing to set" in result


def test_set_exit_rule_persists_stop_loss_and_take_profit(tmp_path):
    store = _confirmed_holding(tmp_path)
    result = SetCryptoExitRuleTool(store).run(
        portfolio="stable", coin="bitcoin", stop_loss_price=90, take_profit_price=150
    )
    assert "stop-loss 90" in result
    assert "take-profit 150" in result
    holding = store.list_crypto_holdings("stable")[0]
    assert holding.stop_loss_price == 90
    assert holding.take_profit_price == 150


def test_set_exit_rule_time_limit_converts_hours_to_a_future_timestamp(tmp_path):
    store = _confirmed_holding(tmp_path)
    before = time.time()
    SetCryptoExitRuleTool(store).run(portfolio="stable", coin="bitcoin", time_limit_hours=1)
    holding = store.list_crypto_holdings("stable")[0]
    assert holding.exit_time_limit_at > before


def test_set_exit_rule_clear_removes_all_rules(tmp_path):
    store = _confirmed_holding(tmp_path)
    SetCryptoExitRuleTool(store).run(portfolio="stable", coin="bitcoin", stop_loss_price=90)
    result = SetCryptoExitRuleTool(store).run(portfolio="stable", coin="bitcoin", clear=True)
    assert "Cleared exit rules" in result
    holding = store.list_crypto_holdings("stable")[0]
    assert holding.stop_loss_price is None


def test_check_exit_conditions_reports_no_watched_holdings(tmp_path):
    store = _confirmed_holding(tmp_path)
    result = CheckCryptoExitConditionsTool(store).run()
    assert "No holdings have exit rules set" in result


def test_check_exit_conditions_flags_stop_loss_hit(monkeypatch, tmp_path):
    store = _confirmed_holding(tmp_path, price=100.0)
    SetCryptoExitRuleTool(store).run(portfolio="stable", coin="bitcoin", stop_loss_price=90)
    _mock_price_response(
        monkeypatch, {"bitcoin": {"usd": 80, "usd_24h_change": 0, "usd_market_cap": 0, "usd_24h_vol": 0}}
    )

    result = CheckCryptoExitConditionsTool(store).run()

    assert "Triggered" in result
    assert "STOP-LOSS hit" in result


def test_check_exit_conditions_flags_take_profit_hit(monkeypatch, tmp_path):
    store = _confirmed_holding(tmp_path, price=100.0)
    SetCryptoExitRuleTool(store).run(portfolio="stable", coin="bitcoin", take_profit_price=120)
    _mock_price_response(
        monkeypatch, {"bitcoin": {"usd": 150, "usd_24h_change": 0, "usd_market_cap": 0, "usd_24h_vol": 0}}
    )

    result = CheckCryptoExitConditionsTool(store).run()

    assert "TAKE-PROFIT hit" in result


def test_check_exit_conditions_flags_time_limit_expired(monkeypatch, tmp_path):
    store = _confirmed_holding(tmp_path, price=100.0)
    store.set_crypto_exit_rule("stable", "bitcoin", exit_time_limit_at=time.time() - 1)
    _mock_price_response(
        monkeypatch, {"bitcoin": {"usd": 100, "usd_24h_change": 0, "usd_market_cap": 0, "usd_24h_vol": 0}}
    )

    result = CheckCryptoExitConditionsTool(store).run()

    assert "TIME LIMIT expired" in result


def test_check_exit_conditions_reports_not_triggered_when_nothing_crossed(monkeypatch, tmp_path):
    store = _confirmed_holding(tmp_path, price=100.0)
    SetCryptoExitRuleTool(store).run(portfolio="stable", coin="bitcoin", stop_loss_price=50)
    _mock_price_response(
        monkeypatch, {"bitcoin": {"usd": 100, "usd_24h_change": 0, "usd_market_cap": 0, "usd_24h_vol": 0}}
    )

    result = CheckCryptoExitConditionsTool(store).run()

    assert "Not triggered" in result
    assert "no condition triggered" in result


# --- loss-streak guardrail ---


def _confirm_sell(store, portfolio, coin, buy_price, sell_price, quantity=1.0):
    buy_id = store.propose_crypto_trade(
        portfolio=portfolio, action="buy", coin=coin, quantity=quantity, price_usd=buy_price, reasoning="x"
    )
    store.confirm_crypto_trade(buy_id)
    sell_id = store.propose_crypto_trade(
        portfolio=portfolio, action="sell", coin=coin, quantity=quantity, price_usd=sell_price, reasoning="x"
    )
    store.confirm_crypto_trade(sell_id)


def test_loss_streak_status_reports_zero_with_no_history(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    result = GetCryptoLossStreakStatusTool(store).run(portfolio="stable")
    assert "no active losing streak" in result


def test_loss_streak_status_counts_consecutive_losses(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    _confirm_sell(store, "stable", "bitcoin", buy_price=100, sell_price=90)  # loss
    _confirm_sell(store, "stable", "bitcoin", buy_price=100, sell_price=80)  # loss

    result = GetCryptoLossStreakStatusTool(store).run(portfolio="stable")

    assert "2 consecutive losing" in result


def test_loss_streak_stops_at_first_winning_sell(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    _confirm_sell(store, "stable", "bitcoin", buy_price=100, sell_price=150)  # win
    _confirm_sell(store, "stable", "bitcoin", buy_price=100, sell_price=80)  # loss

    result = GetCryptoLossStreakStatusTool(store).run(portfolio="stable")

    assert "1 consecutive losing" in result


def test_loss_streak_reaches_guardrail_threshold_warning(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    for _ in range(_LOSS_STREAK_WARNING_THRESHOLD):
        _confirm_sell(store, "stable", "bitcoin", buy_price=100, sell_price=90)

    result = GetCryptoLossStreakStatusTool(store).run(portfolio="stable")

    assert "Guardrail threshold reached" in result


def test_propose_trade_appends_guardrail_warning_after_loss_streak(monkeypatch, tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    for _ in range(_LOSS_STREAK_WARNING_THRESHOLD):
        _confirm_sell(store, "risky", "bitcoin", buy_price=100, sell_price=90)
    _mock_price_response(
        monkeypatch, {"ethereum": {"usd": 3000, "usd_24h_change": 0, "usd_market_cap": 0, "usd_24h_vol": 0}}
    )

    result = ProposeCryptoTradeTool(store).run(
        portfolio="risky", action="buy", coin="ethereum", quantity=1, reasoning="x"
    )

    assert "PENDING" in result
    assert "Guardrail" in result
    assert "consecutive losing confirmed sells" in result


def test_propose_trade_has_no_guardrail_warning_without_a_loss_streak(monkeypatch, tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    _mock_price_response(
        monkeypatch, {"bitcoin": {"usd": 100, "usd_24h_change": 0, "usd_market_cap": 0, "usd_24h_vol": 0}}
    )

    result = ProposeCryptoTradeTool(store).run(
        portfolio="fresh", action="buy", coin="bitcoin", quantity=1, reasoning="x"
    )

    assert "Guardrail" not in result


# --- suggest_portfolio_rebalance ---


def test_rebalance_reports_no_holdings(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    result = SuggestPortfolioRebalanceTool(store).run(
        portfolio="stable", target_allocations={"bitcoin": 100}
    )
    assert "No holdings recorded" in result


def test_rebalance_flags_overweight_and_underweight(monkeypatch, tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    btc_id = store.propose_crypto_trade(
        portfolio="stable", action="buy", coin="bitcoin", quantity=8, price_usd=100, reasoning="x"
    )
    store.confirm_crypto_trade(btc_id)
    eth_id = store.propose_crypto_trade(
        portfolio="stable", action="buy", coin="ethereum", quantity=2, price_usd=100, reasoning="x"
    )
    store.confirm_crypto_trade(eth_id)
    # Current value: 800 bitcoin (80%), 200 ethereum (20%). Target: 50/50.
    _mock_price_response(
        monkeypatch,
        {
            "bitcoin": {"usd": 100, "usd_24h_change": 0, "usd_market_cap": 0, "usd_24h_vol": 0},
            "ethereum": {"usd": 100, "usd_24h_change": 0, "usd_market_cap": 0, "usd_24h_vol": 0},
        },
    )

    result = SuggestPortfolioRebalanceTool(store).run(
        portfolio="stable", target_allocations={"bitcoin": 50, "ethereum": 50}
    )

    assert "bitcoin: 80.0% vs target 50.0% — overweight by 30.0pp" in result
    assert "ethereum: 20.0% vs target 50.0% — underweight by 30.0pp" in result


def test_rebalance_rejects_non_positive_target_sum(tmp_path):
    store = _confirmed_holding(tmp_path)
    result = SuggestPortfolioRebalanceTool(store).run(portfolio="stable", target_allocations={"bitcoin": 0})
    assert "must sum to a positive number" in result
