import datetime

from tools.info_tools import CryptoPriceTool, CurrencyConversionTool, HistoricalWeatherTool, WeatherTool


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


def _fake_weather_forecast(num_days: int) -> dict:
    return {
        "current": {
            "temperature_2m": 15.0,
            "relative_humidity_2m": 60,
            "weather_code": 2,
            "wind_speed_10m": 10.0,
        },
        "daily": {
            "time": [f"2026-08-{13 + i:02d}" for i in range(num_days)],
            "temperature_2m_max": [20.0 + i for i in range(num_days)],
            "temperature_2m_min": [10.0 + i for i in range(num_days)],
            "weather_code": [0, 61, 3, 95, 1, 2, 71][:num_days],
            "precipitation_probability_max": [5, 80, 20, 90, 10, 15, 40][:num_days],
        },
    }


def _fake_geo_and_forecast(monkeypatch, forecast_response: dict):
    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return _FakeResponse({"results": [{"name": "Geneva", "country": "Switzerland", "latitude": 46.2, "longitude": 6.15}]})
        return _FakeResponse(forecast_response)

    monkeypatch.setattr("tools.info_tools.client.get", fake_get)


def test_weather_default_forecast_days_is_today_only(monkeypatch):
    _fake_geo_and_forecast(monkeypatch, _fake_weather_forecast(1))

    result = WeatherTool().run(city="Geneva")

    assert "Today:" in result
    assert "Tomorrow:" not in result


def test_weather_multi_day_forecast_includes_tomorrow_labeled_explicitly(monkeypatch):
    """Regression test: the tool used to only ever report today's range
    (daily[...][0]) even though Open-Meteo already returns a full week by
    default — Orion telling the user it "couldn't look at tomorrow's
    weather" was a tool-description/parameter gap, not a real API
    limitation."""
    _fake_geo_and_forecast(monkeypatch, _fake_weather_forecast(3))

    result = WeatherTool().run(city="Geneva", forecast_days=3)

    assert "Today:" in result
    assert "Tomorrow:" in result
    assert "10.0°C to 20.0°C" in result  # today's (index 0) min/max
    assert "11.0°C to 21.0°C" in result  # tomorrow's (index 1) min/max, distinct from today's


def test_weather_includes_rain_chance_and_condition_description(monkeypatch):
    _fake_geo_and_forecast(monkeypatch, _fake_weather_forecast(2))

    result = WeatherTool().run(city="Geneva", forecast_days=2)

    assert "80% chance of rain" in result  # tomorrow's precipitation_probability_max
    assert "slight rain" in result  # weather_code 61 for tomorrow


def test_weather_forecast_days_is_clamped_not_rejected(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return _FakeResponse({"results": [{"name": "Geneva", "country": "CH", "latitude": 1, "longitude": 2}]})
        calls.append(params["forecast_days"])
        return _FakeResponse(_fake_weather_forecast(7))

    monkeypatch.setattr("tools.info_tools.client.get", fake_get)

    WeatherTool().run(city="Geneva", forecast_days=30)

    assert calls == [7]  # clamped to the 7-day cap, not passed through or rejected


def test_weather_unknown_weather_code_degrades_gracefully(monkeypatch):
    forecast = _fake_weather_forecast(1)
    forecast["current"]["weather_code"] = 9999  # not in the WMO table
    _fake_geo_and_forecast(monkeypatch, forecast)

    result = WeatherTool().run(city="Geneva")

    assert "unknown conditions" in result
