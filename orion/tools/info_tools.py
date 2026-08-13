"""General knowledge / live-data tools that need no API key — all built on
free public APIs (Open-Meteo, Wikipedia, sunrise-sunset.org, frankfurter.app,
stooq, Google News RSS, CoinGecko, dictionaryapi.dev)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from urllib.parse import quote

import httpx

from core.http import client
from tools.base import Tool


# WMO weather interpretation codes (the same table Open-Meteo's API docs
# publish for its weather_code field, and what every "daily" forecast day
# comes back tagged with) — condensed to the phrasing that actually matters
# for a spoken/read-aloud summary rather than the full meteorological detail.
_WMO_WEATHER_DESCRIPTIONS = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    56: "light freezing drizzle", 57: "dense freezing drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    66: "light freezing rain", 67: "heavy freezing rain",
    71: "slight snow", 73: "moderate snow", 75: "heavy snow", 77: "snow grains",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    85: "slight snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with slight hail", 99: "thunderstorm with heavy hail",
}


def _describe_weather_code(code: int | None) -> str:
    if code is None:
        return "unknown conditions"
    return _WMO_WEATHER_DESCRIPTIONS.get(code, "unknown conditions")


class WeatherTool(Tool):
    name = "get_weather"
    description = (
        "Get the current weather for a city, plus a daily forecast — pass forecast_days "
        "(1 = today only, up to 7 = a week ahead) to answer 'what's the weather tomorrow/"
        "this weekend/next week' instead of only today."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name, e.g. 'Paris' or 'Montreal'."},
            "forecast_days": {
                "type": "integer",
                "description": "How many days ahead to include, starting today (index 0 = today, "
                "1 = tomorrow, ...). Default 1 (today only). Open-Meteo supports up to 16; capped "
                "at 7 here since anything further out is low-confidence.",
            },
        },
        "required": ["city"],
    }

    def run(self, city: str, forecast_days: int = 1) -> str:
        # Clamped rather than rejected: Claude asking for "the next two
        # weeks" shouldn't error out, it should just get the most it
        # reasonably can (day-8+ forecasts are low-confidence anyway).
        forecast_days = max(1, min(forecast_days, 7))

        geo = client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
            timeout=10,
        ).json()
        results = geo.get("results")
        if not results:
            return f"Could not find a location named '{city}'."
        place = results[0]

        weather = client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
                "forecast_days": forecast_days,
                "timezone": "auto",
                # Open-Meteo's default model-selection mode: for any given
                # coordinate it automatically picks the highest-resolution
                # model actually covering that location — for Switzerland
                # specifically that's MeteoSwiss's own ICON-CH1/CH2 model
                # (1-2km resolution), not a generic global model. Passed
                # explicitly here (it's already the default) so this
                # behavior doesn't silently change if that default ever
                # does.
                "models": "best_match",
            },
            timeout=10,
        ).json()

        current = weather["current"]
        daily = weather["daily"]
        location = f"{place['name']}, {place.get('country', '')}"

        lines = [
            f"Weather in {location}: {current['temperature_2m']}°C now "
            f"(humidity {current['relative_humidity_2m']}%), wind {current['wind_speed_10m']} km/h, "
            f"{_describe_weather_code(current.get('weather_code'))}."
        ]

        dates = daily.get("time", [])
        for i in range(len(dates)):
            label = "Today" if i == 0 else ("Tomorrow" if i == 1 else dates[i])
            rain_chance = daily.get("precipitation_probability_max", [None] * len(dates))[i]
            rain_note = f", {rain_chance}% chance of rain" if rain_chance is not None else ""
            lines.append(
                f"{label}: {daily['temperature_2m_min'][i]}°C to {daily['temperature_2m_max'][i]}°C, "
                f"{_describe_weather_code(daily['weather_code'][i])}{rain_note}."
            )

        return " ".join(lines)


class SunTimesTool(Tool):
    name = "get_sun_times"
    description = "Get today's sunrise and sunset times for a city."
    input_schema = {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    }

    def run(self, city: str) -> str:
        geo = client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
            timeout=10,
        ).json()
        results = geo.get("results")
        if not results:
            return f"Could not find a location named '{city}'."
        place = results[0]

        data = client.get(
            "https://api.sunrise-sunset.org/json",
            params={"lat": place["latitude"], "lng": place["longitude"], "formatted": 0},
            timeout=10,
        ).json()["results"]
        return f"Sunrise in {place['name']}: {data['sunrise']}, sunset: {data['sunset']} (UTC)."


class WikipediaSummaryTool(Tool):
    name = "wikipedia_summary"
    description = "Get a short Wikipedia summary of a topic."
    input_schema = {
        "type": "object",
        "properties": {"topic": {"type": "string"}},
        "required": ["topic"],
    }

    def run(self, topic: str) -> str:
        response = client.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(topic)}",
            timeout=10,
            follow_redirects=True,
        )
        if response.status_code != 200:
            return f"No Wikipedia article found for '{topic}'."
        data = response.json()
        return data.get("extract", f"No summary available for '{topic}'.")


class CurrencyConversionTool(Tool):
    name = "convert_currency"
    description = "Convert an amount from one currency to another using current exchange rates."
    input_schema = {
        "type": "object",
        "properties": {
            "amount": {"type": "number"},
            "from_currency": {"type": "string", "description": "3-letter code, e.g. 'USD'."},
            "to_currency": {"type": "string", "description": "3-letter code, e.g. 'EUR'."},
        },
        "required": ["amount", "from_currency", "to_currency"],
    }

    def run(self, amount: float, from_currency: str, to_currency: str) -> str:
        from_currency, to_currency = from_currency.upper(), to_currency.upper()
        # frankfurter.app omits the base currency from `rates` when it's
        # the same as `to` (converting a currency to itself is "trivial"
        # so it leaves it out) — this used to read that as "no rate found"
        # and wrongly report a completely valid 1:1 conversion as failed.
        if from_currency == to_currency:
            return f"{amount} {from_currency} = {amount} {to_currency}"
        response = client.get(
            "https://api.frankfurter.app/latest",
            params={"amount": amount, "from": from_currency, "to": to_currency},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        rate = data["rates"].get(to_currency)
        if rate is None:
            return f"Could not convert {from_currency} to {to_currency}."
        return f"{amount} {from_currency} = {rate} {to_currency}"


class StockPriceTool(Tool):
    name = "get_stock_price"
    description = "Get the latest price for a stock ticker (e.g. 'AAPL', 'MSFT')."
    input_schema = {
        "type": "object",
        "properties": {"ticker": {"type": "string"}},
        "required": ["ticker"],
    }

    def run(self, ticker: str) -> str:
        response = client.get(
            "https://stooq.com/q/l/",
            params={"s": f"{ticker.lower()}.us", "f": "sd2t2ohlcv", "h": "", "e": "csv"},
            timeout=10,
        )
        lines = response.text.strip().splitlines()
        if len(lines) < 2:
            return f"No data found for ticker '{ticker}'."
        header, values = lines[0].split(","), lines[1].split(",")
        record = dict(zip(header, values))
        if record.get("Close") in (None, "N/D"):
            return f"No data found for ticker '{ticker}'."
        return f"{ticker.upper()}: {record['Close']} (as of {record['Date']} {record['Time']})"


class CryptoPriceTool(Tool):
    name = "get_crypto_price"
    description = "Get the current price of a cryptocurrency (e.g. 'bitcoin', 'ethereum') in a given currency."
    input_schema = {
        "type": "object",
        "properties": {
            "coin": {"type": "string", "description": "CoinGecko coin id, e.g. 'bitcoin', 'ethereum', 'solana'."},
            "vs_currency": {"type": "string", "description": "Default 'usd'."},
        },
        "required": ["coin"],
    }

    def run(self, coin: str, vs_currency: str = "usd") -> str:
        response = client.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": coin.lower(), "vs_currencies": vs_currency.lower()},
            timeout=10,
        )
        data = response.json()
        if coin.lower() not in data:
            return f"No price found for '{coin}'. Use the CoinGecko coin id, e.g. 'bitcoin' not 'BTC'."
        # CoinGecko returns the coin key present but with an *empty* inner
        # object when vs_currency isn't one it recognizes — checking only
        # the outer key used to let an unsupported/misspelled currency
        # through to a raw KeyError instead of a clean message.
        price = data[coin.lower()].get(vs_currency.lower())
        if price is None:
            return f"'{vs_currency}' isn't a currency CoinGecko recognizes for '{coin}'."
        return f"{coin} = {price} {vs_currency.upper()}"


class DictionaryTool(Tool):
    name = "define_word"
    description = "Get the definition(s), part of speech, and phonetics of an English word."
    input_schema = {
        "type": "object",
        "properties": {"word": {"type": "string"}},
        "required": ["word"],
    }

    def run(self, word: str) -> str:
        response = client.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(word)}", timeout=10)
        if response.status_code != 200:
            return f"No definition found for '{word}'."

        entries = response.json()
        lines = []
        for entry in entries:
            for meaning in entry.get("meanings", []):
                part_of_speech = meaning.get("partOfSpeech", "")
                for definition in meaning.get("definitions", [])[:2]:
                    lines.append(f"({part_of_speech}) {definition.get('definition', '')}")
        return "\n".join(lines) if lines else f"No definition found for '{word}'."


class HistoricalWeatherTool(Tool):
    name = "get_historical_weather"
    description = "Compare today's weather in a city to the same date in previous years."
    input_schema = {
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "years_back": {"type": "integer", "description": "How many previous years to compare. Default 3."},
        },
        "required": ["city"],
    }

    def run(self, city: str, years_back: int = 3) -> str:
        geo = client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
            timeout=10,
        ).json()
        results = geo.get("results")
        if not results:
            return f"Could not find a location named '{city}'."
        place = results[0]

        today = date.today()
        lines = []
        for years in range(1, years_back + 1):
            try:
                past_date = today.replace(year=today.year - years)
            except ValueError:
                # today.replace(year=...) raises on Feb 29 whenever the
                # target year isn't a leap year (3 of every 4 years_back
                # values, any time this runs on a leap day) — that used to
                # abort the whole comparison instead of just skipping the
                # one year that genuinely has no Feb 29 to compare against.
                continue
            data = client.get(
                "https://archive-api.open-meteo.com/v1/archive",
                params={
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "start_date": past_date.isoformat(),
                    "end_date": past_date.isoformat(),
                    "daily": "temperature_2m_max,temperature_2m_min",
                    "timezone": "auto",
                },
                timeout=10,
            ).json()
            daily = data.get("daily", {})
            if daily.get("temperature_2m_max"):
                lines.append(
                    f"{past_date}: {daily['temperature_2m_min'][0]}°C to {daily['temperature_2m_max'][0]}°C"
                )

        return "\n".join(lines) if lines else f"No historical data available for {city}."


class NewsHeadlinesTool(Tool):
    name = "get_news_headlines"
    description = "Get recent news headlines, optionally filtered by topic/keyword."
    input_schema = {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Optional keyword/topic to search news for."},
            "max_results": {"type": "integer", "description": "Max headlines to return (default 8)."},
        },
    }

    def run(self, topic: str | None = None, max_results: int = 8) -> str:
        query = topic or ""
        response = client.get(
            "https://news.google.com/rss/search" if query else "https://news.google.com/rss",
            params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"} if query else None,
            timeout=10,
        )
        root = ET.fromstring(response.text)
        items = root.findall(".//item")[:max_results]
        if not items:
            return "No headlines found."
        lines = []
        for item in items:
            title = item.findtext("title", default="")
            pub_date = item.findtext("pubDate", default="")
            lines.append(f"- {title} ({pub_date})")
        return "\n".join(lines)
