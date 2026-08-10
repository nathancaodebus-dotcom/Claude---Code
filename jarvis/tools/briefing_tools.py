"""Morning briefing / evening debrief: composite tools that pull from
whatever other tools happen to be registered (weather, calendar, todos,
news, system status) rather than duplicating their logic. If a given source
isn't configured (e.g. no Home Assistant), its section is just omitted.
"""
from __future__ import annotations

from core.config import config
from tools.base import Tool, ToolRegistry


class MorningBriefingTool(Tool):
    name = "morning_briefing"
    description = (
        "Give the user a morning briefing: weather, today's calendar, open to-dos, and "
        "top news headlines. Call this when the user asks for their morning briefing/summary."
    )
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    def run(self) -> str:
        sections = []

        if config.home_city and self._registry.get("get_weather"):
            sections.append("WEATHER:\n" + self._registry.dispatch("get_weather", {"city": config.home_city}))

        if self._registry.get("list_calendar_events"):
            sections.append(
                "TODAY'S CALENDAR:\n" + self._registry.dispatch("list_calendar_events", {"days_ahead": 1})
            )

        if self._registry.get("list_todos"):
            sections.append("OPEN TO-DOS:\n" + self._registry.dispatch("list_todos", {}))

        if self._registry.get("get_news_headlines"):
            sections.append(
                "TOP HEADLINES:\n" + self._registry.dispatch("get_news_headlines", {"max_results": 5})
            )

        if not sections:
            return "No briefing sources configured (weather/calendar/todos/news)."
        return "\n\n".join(sections)


class EveningDebriefTool(Tool):
    name = "evening_debrief"
    description = (
        "Give the user an evening debrief: to-dos completed today, tomorrow's calendar, and "
        "a reminder to handle any lights/devices still on. Call this when the user asks for "
        "their evening recap/debrief."
    )
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    def run(self) -> str:
        sections = []

        if self._registry.get("list_todos"):
            sections.append("REMAINING OPEN TO-DOS:\n" + self._registry.dispatch("list_todos", {}))

        if self._registry.get("list_calendar_events"):
            sections.append(
                "TOMORROW ONWARD:\n" + self._registry.dispatch("list_calendar_events", {"days_ahead": 2})
            )

        if self._registry.get("list_smart_home_devices"):
            devices = self._registry.dispatch("list_smart_home_devices", {"domain": "light"})
            sections.append("LIGHTS CURRENTLY ON (consider turning off):\n" + devices)

        if not sections:
            return "No debrief sources configured (todos/calendar/smart home)."
        return "\n\n".join(sections)
