from tools.crypto_backtest_tool import BacktestCryptoSignalTool, _fetch_binance_klines


def _kline(open_time_ms, close):
    return [open_time_ms, close - 1, close + 1, close - 2, close, 1000.0, 0, "0", 1, "0", "0", "0"]


def _klines_payload(n, start_close=100.0):
    return [_kline(i * 3_600_000, start_close + i) for i in range(n)]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_fetch_binance_klines_parses_ohlcv(monkeypatch):
    monkeypatch.setattr(
        "tools.crypto_backtest_tool.client.get", lambda *a, **kw: _FakeResponse(_klines_payload(3))
    )
    bars = _fetch_binance_klines("BTC", "USDT", "1d", 3)
    assert len(bars) == 3
    assert bars[0]["close"] == 100.0
    assert bars[2]["close"] == 102.0


def test_fetch_binance_klines_handles_error_payload(monkeypatch):
    """Binance reports an unknown symbol as {"code": -1121, "msg": "..."} —
    a dict, not a list — rather than raising or returning an empty list."""
    monkeypatch.setattr(
        "tools.crypto_backtest_tool.client.get",
        lambda *a, **kw: _FakeResponse({"code": -1121, "msg": "Invalid symbol."}),
    )
    assert _fetch_binance_klines("NOTREAL", "USDT", "1d", 10) == []


def test_backtest_not_enough_history(monkeypatch):
    monkeypatch.setattr(
        "tools.crypto_backtest_tool.client.get", lambda *a, **kw: _FakeResponse(_klines_payload(5))
    )
    result = BacktestCryptoSignalTool().run(
        symbol="BTC", signal_code="def signal(bars):\n    return [1] * len(bars)\n"
    )
    assert "Not enough price history" in result


def test_backtest_rejects_a_non_positive_forward_days():
    result = BacktestCryptoSignalTool().run(
        symbol="BTC", signal_code="def signal(bars):\n    return [1] * len(bars)\n", forward_days=0
    )
    assert "forward_days must be" in result


def test_backtest_rejects_an_invalid_interval():
    result = BacktestCryptoSignalTool().run(
        symbol="BTC", signal_code="def signal(bars):\n    return [1] * len(bars)\n", interval="1m"
    )
    assert "interval must be one of" in result


def test_backtest_computes_ic_for_a_real_signal(monkeypatch):
    monkeypatch.setattr(
        "tools.crypto_backtest_tool.client.get", lambda *a, **kw: _FakeResponse(_klines_payload(60))
    )
    signal_code = (
        "def signal(bars):\n"
        "    out = []\n"
        "    for i in range(len(bars)):\n"
        "        out.append(bars[i]['close'])\n"
        "    return out\n"
    )
    result = BacktestCryptoSignalTool().run(symbol="BTC", signal_code=signal_code, forward_days=3)
    assert "BTC/USDT (1d)" in result
    assert "Rank IC" in result


def test_backtest_caps_lookback_bars_at_binance_limit(monkeypatch):
    captured = {}

    def fake_get(*a, **kw):
        captured["limit"] = kw["params"]["limit"]
        return _FakeResponse(_klines_payload(5))

    monkeypatch.setattr("tools.crypto_backtest_tool.client.get", fake_get)
    BacktestCryptoSignalTool().run(
        symbol="BTC", signal_code="def signal(bars):\n    return [1] * len(bars)\n", lookback_bars=5000
    )
    assert captured["limit"] == 1000
