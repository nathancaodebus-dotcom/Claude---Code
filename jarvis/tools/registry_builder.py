"""Assembles the ToolRegistry, enabling each integration only if it's configured.

This is what makes 'add a new capability' a one-file change: implement a
Tool subclass, register it here behind whatever config check makes sense,
and it's immediately available to the agent loop and every interface.
"""
from __future__ import annotations

from core.config import config
from core.memory import Memory
from core.store import Store
from tools.base import ToolRegistry
from tools.fun_tools import CoinFlipTool, JokeTool, MagicEightBallTool, RandomQuoteTool, RollDiceTool
from tools.info_tools import (
    CurrencyConversionTool,
    NewsHeadlinesTool,
    StockPriceTool,
    SunTimesTool,
    WeatherTool,
    WikipediaSummaryTool,
)
from tools.memory_tool import RecallFactsTool, RememberFactTool
from tools.productivity_tools import (
    AddNoteTool,
    AddShoppingItemTool,
    AddTodoTool,
    CancelReminderTool,
    ClearShoppingListTool,
    CompleteTodoTool,
    ListNotesTool,
    ListRemindersTool,
    ListShoppingListTool,
    ListTodosTool,
    SetReminderTool,
)
from tools.system_tool import SystemStatusTool
from tools.utility_tools import CalculatorTool, GeneratePasswordTool, GenerateQrCodeTool, UnitConversionTool
from tools.web_tools import FetchWebpageTool, PublicIpTool, ShortenUrlTool, WebSearchTool


def build_registry(memory: Memory, store: Store | None = None) -> ToolRegistry:
    registry = ToolRegistry()
    store = store or Store()

    # Memory
    registry.register(RememberFactTool(memory))
    registry.register(RecallFactsTool(memory))

    # Productivity (todos, notes, shopping list, reminders/timers)
    registry.register(AddTodoTool(store))
    registry.register(ListTodosTool(store))
    registry.register(CompleteTodoTool(store))
    registry.register(AddNoteTool(store))
    registry.register(ListNotesTool(store))
    registry.register(AddShoppingItemTool(store))
    registry.register(ListShoppingListTool(store))
    registry.register(ClearShoppingListTool(store))
    registry.register(SetReminderTool(store))
    registry.register(ListRemindersTool(store))
    registry.register(CancelReminderTool(store))

    # Live info (no API key needed)
    registry.register(WeatherTool())
    registry.register(SunTimesTool())
    registry.register(WikipediaSummaryTool())
    registry.register(CurrencyConversionTool())
    registry.register(StockPriceTool())
    registry.register(NewsHeadlinesTool())

    # Open web
    registry.register(WebSearchTool())
    registry.register(FetchWebpageTool())
    registry.register(ShortenUrlTool())
    registry.register(PublicIpTool())

    # Fun
    registry.register(CoinFlipTool())
    registry.register(RollDiceTool())
    registry.register(MagicEightBallTool())
    registry.register(RandomQuoteTool())
    registry.register(JokeTool())

    # Utilities
    registry.register(CalculatorTool())
    registry.register(UnitConversionTool())
    registry.register(GeneratePasswordTool())
    registry.register(GenerateQrCodeTool())

    # Self-monitoring
    registry.register(SystemStatusTool())

    if config.google_credentials_path:
        try:
            from tools.calendar_tool import CreateEventTool, ListEventsTool
            from tools.gmail_tool import GmailReadTool, GmailSearchTool

            registry.register(GmailSearchTool())
            registry.register(GmailReadTool())
            registry.register(ListEventsTool())
            registry.register(CreateEventTool())
        except ImportError:
            pass  # google-api-python-client not installed; Gmail/Calendar tools stay disabled

    if config.home_assistant_url and config.home_assistant_token:
        from tools.home_assistant_tool import CallServiceTool, ListDevicesTool

        registry.register(ListDevicesTool())
        registry.register(CallServiceTool())

    return registry
