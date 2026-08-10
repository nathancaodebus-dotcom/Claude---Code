"""General knowledge / live-data tools that need no API key — all built on
free public APIs (Open-Meteo, Wikipedia, sunrise-sunset.org, frankfurter.app,
stooq, Google News RSS)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import quote

import httpx

from tools.base import Tool


class WeatherTool(Tool):
    name = "get_weather"
    description = "Get the current weather and today's forecast for a city."
    input_schema = {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "City name, e.g. 'Paris' or 'Montreal'."}},
        "required": ["city"],
    }

    def run(self, city: str) -> str:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
            timeout=10,
        ).json()
        results = geo.get("results")
        if not results:
            return f"Could not find a location named '{city}'."
        place = results[0]

        weather = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min",
                "timezone": "auto",
            },
            timeout=10,
        ).json()

        current = weather["current"]
        daily = weather["daily"]
        return (
            f"Weather in {place['name']}, {place.get('country', '')}: "
            f"{current['temperature_2m']}°C now (feels via humidity {current['relative_humidity_2m']}%), "
            f"wind {current['wind_speed_10m']} km/h. "
            f"Today's range: {daily['temperature_2m_min'][0]}°C to {daily['temperature_2m_max'][0]}°C."
        )


class SunTimesTool(Tool):
    name = "get_sun_times"
    description = "Get today's sunrise and sunset times for a city."
    input_schema = {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    }

    def run(self, city: str) -> str:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
            timeout=10,
        ).json()
        results = geo.get("results")
        if not results:
            return f"Could not find a location named '{city}'."
        place = results[0]

        data = httpx.get(
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
        response = httpx.get(
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
        data = httpx.get(
            "https://api.frankfurter.app/latest",
            params={"amount": amount, "from": from_currency.upper(), "to": to_currency.upper()},
            timeout=10,
        ).json()
        rate = data["rates"].get(to_currency.upper())
        if rate is None:
            return f"Could not convert {from_currency} to {to_currency}."
        return f"{amount} {from_currency.upper()} = {rate} {to_currency.upper()}"


class StockPriceTool(Tool):
    name = "get_stock_price"
    description = "Get the latest price for a stock ticker (e.g. 'AAPL', 'MSFT')."
    input_schema = {
        "type": "object",
        "properties": {"ticker": {"type": "string"}},
        "required": ["ticker"],
    }

    def run(self, ticker: str) -> str:
        response = httpx.get(
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
        response = httpx.get(
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
