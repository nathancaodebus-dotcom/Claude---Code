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
from tools.docx_tools import AppendToWordDocumentTool, CreateWordDocumentTool, ListWordDocumentsTool
from tools.pptx_tools import (
    AddSlideTool,
    CreatePresentationTool,
    DeleteSlideTool,
    EditSlideTool,
    ListPresentationsTool,
    ListSlidesTool,
)
from tools.system_tool import SystemStatusTool
from tools.utility_tools import CalculatorTool, GeneratePasswordTool, GenerateQrCodeTool, UnitConversionTool
from tools.web_tools import FetchWebpageTool, PublicIpTool, ShortenUrlTool, WebSearchTool
from tools.xlsx_tools import AddSpreadsheetRowTool, CreateSpreadsheetTool, ListSpreadsheetsTool


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

    # Office documents (PowerPoint, Word, Excel) — create and edit by voice/text
    registry.register(CreatePresentationTool(store))
    registry.register(AddSlideTool(store))
    registry.register(EditSlideTool(store))
    registry.register(DeleteSlideTool(store))
    registry.register(ListSlidesTool(store))
    registry.register(ListPresentationsTool(store))
    registry.register(CreateWordDocumentTool(store))
    registry.register(AppendToWordDocumentTool(store))
    registry.register(ListWordDocumentsTool(store))
    registry.register(CreateSpreadsheetTool(store))
    registry.register(AddSpreadsheetRowTool(store))
    registry.register(ListSpreadsheetsTool(store))

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

    if config.spotify_client_id and config.spotify_client_secret:
        try:
            from tools.spotify_tools import (
                ListSpotifyDevicesTool,
                PauseSpotifyTool,
                PlaySpotifyTool,
                ResumeSpotifyTool,
                SearchSpotifyTool,
                SetSpotifyVolumeTool,
                SkipSpotifyTool,
            )

            registry.register(SearchSpotifyTool())
            registry.register(PlaySpotifyTool())
            registry.register(PauseSpotifyTool())
            registry.register(ResumeSpotifyTool())
            registry.register(SkipSpotifyTool())
            registry.register(SetSpotifyVolumeTool())
            registry.register(ListSpotifyDevicesTool())
        except ImportError:
            pass  # spotipy not installed; Spotify tools stay disabled

    try:
        from tools.media_tools import (
            LaunchAppOnTvTool,
            ListChromecastsTool,
            PauseCastTool,
            PlayYoutubeVideoTool,
            ResumeCastTool,
            SearchYoutubeTool,
            SetCastVolumeTool,
            StopCastingTool,
        )

        # Casting only needs the local network — no config required, though
        # setting CHROMECAST_NAME saves repeating device_name on every call.
        registry.register(ListChromecastsTool())
        registry.register(LaunchAppOnTvTool())
        registry.register(StopCastingTool())
        registry.register(PauseCastTool())
        registry.register(ResumeCastTool())
        registry.register(SetCastVolumeTool())
        if config.youtube_api_key:
            registry.register(SearchYoutubeTool())
            registry.register(PlayYoutubeVideoTool())
    except ImportError:
        pass  # pychromecast not installed; casting tools stay disabled

    return registry
