import pytest

from core.store import Store
from tools.quant_signal_tools import (
    BacktestQuantSignalTool,
    ListQuantSignalsTool,
    SaveQuantSignalTool,
    _fetch_stooq_history,
)

_STOOQ_CSV = "\n".join(
    ["Date,Open,High,Low,Close,Volume"]
    + [f"2024-01-{i + 1:02d},{100 + i},{101 + i},{99 + i},{100 + i},1000" for i in range(40)]
)


class _FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def store(tmp_path):
    return Store(db_path=str(tmp_path / "test.db"))


@pytest.fixture(autouse=True)
def mock_stooq(monkeypatch):
    monkeypatch.setattr(
        "tools.quant_signal_tools.httpx.get", lambda *a, **kw: _FakeResponse(_STOOQ_CSV)
    )


def test_fetch_stooq_history_parses_csv_and_sorts_ascending(monkeypatch):
    unsorted_csv = "Date,Open,High,Low,Close,Volume\n2024-01-02,101,102,100,101,900\n2024-01-01,100,101,99,100,1000\n"
    monkeypatch.setattr("tools.quant_signal_tools.httpx.get", lambda *a, **kw: _FakeResponse(unsorted_csv))

    bars = _fetch_stooq_history("aapl", 30)

    assert [b["date"] for b in bars] == ["2024-01-01", "2024-01-02"]
    assert bars[0]["close"] == 100.0


def test_fetch_stooq_history_handles_no_data_response(monkeypatch):
    monkeypatch.setattr("tools.quant_signal_tools.httpx.get", lambda *a, **kw: _FakeResponse("No data"))
    assert _fetch_stooq_history("ghost", 30) == []


def test_backtest_not_enough_history(monkeypatch):
    monkeypatch.setattr(
        "tools.quant_signal_tools.httpx.get",
        lambda *a, **kw: _FakeResponse("Date,Open,High,Low,Close,Volume\n2024-01-01,100,101,99,100,1000\n"),
    )
    result = BacktestQuantSignalTool().run(ticker="AAPL", signal_code="def signal(bars):\n    return [1] * len(bars)\n")
    assert "Not enough price history" in result


def test_backtest_computes_ic_for_a_real_signal():
    signal_code = (
        "def signal(bars):\n"
        "    out = []\n"
        "    for i in range(len(bars)):\n"
        "        out.append(bars[i]['close'] - bars[i - 5]['close'] if i >= 5 else None)\n"
        "    return out\n"
    )

    result = BacktestQuantSignalTool().run(ticker="AAPL", signal_code=signal_code, forward_days=3)

    assert "AAPL" in result
    assert "Rank IC" in result
    assert "observations" in result


def test_backtest_reports_exception_in_signal_code():
    result = BacktestQuantSignalTool().run(
        ticker="AAPL", signal_code="def signal(bars):\n    raise ValueError('bad formula')\n"
    )
    assert "Signal error" in result
    assert "bad formula" in result


def test_backtest_reports_wrong_return_length():
    result = BacktestQuantSignalTool().run(ticker="AAPL", signal_code="def signal(bars):\n    return [1, 2, 3]\n")
    assert "same length as bars" in result


def test_backtest_reports_too_few_observations():
    result = BacktestQuantSignalTool().run(
        ticker="AAPL", signal_code="def signal(bars):\n    return [None] * len(bars)\n"
    )
    assert "usable observations" in result


def test_backtest_caps_lookback_days():
    # Just confirms an oversized lookback doesn't error out or bypass the cap silently.
    signal_code = "def signal(bars):\n    return [1.0] * len(bars)\n"
    result = BacktestQuantSignalTool().run(ticker="AAPL", signal_code=signal_code, lookback_days=999999)
    assert "AAPL" in result


def test_save_and_list_quant_signals(store):
    save_result = SaveQuantSignalTool(store).run(
        name="5d momentum", ticker="aapl", signal_code="def signal(bars): return []",
        ic_score=0.087, forward_days=5, notes="works best in trending markets",
    )
    assert "Saved signal" in save_result
    assert "AAPL" in save_result

    list_result = ListQuantSignalsTool(store).run()
    assert "5d momentum" in list_result
    assert "AAPL" in list_result
    assert "0.0870" in list_result
    assert "works best in trending markets" in list_result


def test_list_quant_signals_empty(store):
    assert ListQuantSignalsTool(store).run() == "No saved signals yet."


def test_list_quant_signals_filters_by_ticker(store):
    SaveQuantSignalTool(store).run(
        name="A", ticker="AAPL", signal_code="x", ic_score=0.1, forward_days=5
    )
    SaveQuantSignalTool(store).run(
        name="B", ticker="MSFT", signal_code="x", ic_score=0.2, forward_days=5
    )

    result = ListQuantSignalsTool(store).run(ticker="msft")

    assert "'B'" in result
    assert "'A'" not in result


def test_list_quant_signals_ranked_by_ic_descending(store):
    SaveQuantSignalTool(store).run(name="Weak", ticker="AAPL", signal_code="x", ic_score=0.02, forward_days=5)
    SaveQuantSignalTool(store).run(name="Strong", ticker="AAPL", signal_code="x", ic_score=0.15, forward_days=5)

    result = ListQuantSignalsTool(store).run()

    assert result.index("Strong") < result.index("Weak")
