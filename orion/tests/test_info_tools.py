import datetime

from tools.info_tools import CryptoPriceTool, CurrencyConversionTool, HistoricalWeatherTool


class _FakeResponse:
    def __init__(self, json_data=None, status_code=200):
        self._json_data = json_data or {}
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_convert_currency_same_currency_short_circuits_without_a_network_call(monkeypatch):
    """Regression test: frankfurter.app omits the base currency from
    `rates` when it equals `to` (a trivial 1:1 conversion) — this used to
    read the resulting empty rates dict as 'no rate found' and wrongly
    report a completely valid conversion as failed."""

    def fail_if_called(*a, **kw):
        raise AssertionError("should not make a network call for a same-currency conversion")

    monkeypatch.setattr("tools.info_tools.client.get", fail_if_called)

    result = CurrencyConversionTool().run(amount=10, from_currency="USD", to_currency="usd")

    assert result == "10 USD = 10 USD"


def test_convert_currency_normal_conversion(monkeypatch):
    monkeypatch.setattr(
        "tools.info_tools.client.get", lambda *a, **kw: _FakeResponse({"rates": {"EUR": 9.2}})
    )
    result = CurrencyConversionTool().run(amount=10, from_currency="usd", to_currency="eur")
    assert result == "10 USD = 9.2 EUR"


def test_crypto_price_reports_unsupported_currency_cleanly(monkeypatch):
    """Regression test: CoinGecko returns the coin key present but with an
    *empty* inner object when vs_currency isn't recognized — indexing it
    directly used to raise a raw KeyError instead of a clean message."""
    monkeypatch.setattr("tools.info_tools.client.get", lambda *a, **kw: _FakeResponse({"bitcoin": {}}))

    result = CryptoPriceTool().run(coin="bitcoin", vs_currency="xyz")

    assert "xyz" in result
    assert "recognize" in result.lower()


def test_crypto_price_normal_lookup(monkeypatch):
    monkeypatch.setattr(
        "tools.info_tools.client.get", lambda *a, **kw: _FakeResponse({"bitcoin": {"usd": 65000}})
    )
    result = CryptoPriceTool().run(coin="bitcoin")
    assert "65000" in result


def test_historical_weather_skips_a_leap_day_year_instead_of_crashing(monkeypatch):
    """Regression test: date.replace(year=...) raises ValueError on Feb 29
    whenever the target year isn't a leap year — this used to abort the
    whole comparison (a raw crash) instead of just skipping that one year."""
    calls = []

    class _FakeDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2028, 2, 29)  # 2028 is a leap year

    monkeypatch.setattr("tools.info_tools.date", _FakeDate)

    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return _FakeResponse({"results": [{"latitude": 1.0, "longitude": 2.0}]})
        calls.append(params["start_date"])
        return _FakeResponse({"daily": {"temperature_2m_max": [10.0], "temperature_2m_min": [2.0]}})

    monkeypatch.setattr("tools.info_tools.client.get", fake_get)

    result = HistoricalWeatherTool().run(city="Testville", years_back=4)

    # Of 2024-2027, only 2024 is a leap year — 2025/2026/2027 have no Feb
    # 29 and are skipped without raising, instead of crashing the whole call.
    assert calls == ["2024-02-29"]
    assert "No historical data" not in result
