import httpx
import pytest

from core.store import Store
from tools.crypto_tools import (
    CompareCryptoAssetsTool,
    ConfirmCryptoTradeTool,
    GetCryptoMarketDataTool,
    GetCryptoTechnicalIndicatorsTool,
    ListCryptoHoldingsTool,
    ListPendingCryptoTradesTool,
    ProposeCryptoTradeTool,
    RejectCryptoTradeTool,
    SuggestPositionSizeTool,
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
        "tools.crypto_tools.httpx.get", lambda *a, **kw: _FakeResponse(data)
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
        "tools.crypto_tools.httpx.get", lambda *a, **kw: _FakeResponse({"prices": prices})
    )
    result = GetCryptoTechnicalIndicatorsTool().run(coin="bitcoin", days=30)
    assert "SMA7" in result
    assert "SMA30" in result
    assert "RSI14" in result


def test_technical_indicators_handles_missing_coin(monkeypatch):
    monkeypatch.setattr(
        "tools.crypto_tools.httpx.get", lambda *a, **kw: _FakeResponse({"prices": []})
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
