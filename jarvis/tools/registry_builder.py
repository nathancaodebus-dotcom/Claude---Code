"""Assembles the ToolRegistry, enabling each integration only if it's configured.

This is what makes 'add a new capability' a one-file change: implement a
Tool subclass, register it here behind whatever config check makes sense,
and it's immediately available to the agent loop and every interface.
"""
from __future__ import annotations

from core.config import config
from core.memory import Memory
from core.store import Store
from tools.ambient_sound_tool import GenerateAmbientSoundTool
from tools.backup_tools import RunBackupTool
from tools.base import ToolRegistry
from tools.briefing_tools import EveningDebriefTool, MorningBriefingTool
from tools.chart_tool import GenerateChartTool
from tools.deploy_tool import ListDeployCommandsTool, RunDeployCommandTool
from tools.disk_health_tool import CheckDiskHealthTool
from tools.docx_tools import AppendToWordDocumentTool, CreateWordDocumentTool, ListWordDocumentsTool
from tools.document_reader_tools import ReadPdfTool, ReadWordDocumentTool
from tools.emergency_tool import EmergencyAlertTool
from tools.file_manager_tools import FindDuplicateFilesTool, FindLargeFilesTool, SummarizeDirectoryTool
from tools.flashcard_tool import GenerateFlashcardsTool, GenerateQuizTool
from tools.fun_tools import CoinFlipTool, JokeTool, MagicEightBallTool, RandomQuoteTool, RollDiceTool
from tools.github_watch_tools import LatestGithubReleaseTool, RecentGithubCommitsTool
from tools.image_analysis_tool import AnalyzeImageTool
from tools.info_tools import (
    CryptoPriceTool,
    CurrencyConversionTool,
    DictionaryTool,
    HistoricalWeatherTool,
    NewsHeadlinesTool,
    StockPriceTool,
    SunTimesTool,
    WeatherTool,
    WikipediaSummaryTool,
)
from tools.killswitch_tool import EmergencyWipeTool
from tools.leak_check_tool import CheckEmailBreachedTool, CheckPasswordLeakedTool
from tools.lyrics_tool import GetLyricsTool
from tools.meeting_briefing_tool import PrepareMeetingBriefingTool
from tools.memory_tool import RecallFactsTool, RememberFactTool
from tools.network_tools import NetworkSpeedTestTool
from tools.pptx_tools import (
    AddSlideTool,
    CreatePresentationTool,
    DeleteSlideTool,
    EditSlideTool,
    ListPresentationsTool,
    ListSlidesTool,
)
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
from tools.project_tools import (
    AddMilestoneTool,
    CompleteMilestoneTool,
    CreateProjectTool,
    ListProjectMilestonesTool,
    ListProjectsTool,
)
from tools.rss_reddit_tools import ReadRssFeedTool, RedditTopPostsTool
from tools.security_audit_tools import CheckDependencyVulnerabilitiesTool, SecurityAuditCodeTool
from tools.sql_tool import RunSqlQueryTool
from tools.subagent_tool import DelegateToSubagentTool
from tools.system_tool import (
    ListFailedCommandsTool,
    ListProcessesTool,
    SetProcessPriorityTool,
    SystemStatusTool,
)
from tools.text_file_tool import ReadTextFileTool
from tools.uptime_monitor_tool import CheckMultipleUptimeTool, CheckUptimeTool
from tools.utility_tools import CalculatorTool, GeneratePasswordTool, GenerateQrCodeTool, UnitConversionTool
from tools.web_tools import FetchWebpageTool, PublicIpTool, ShortenUrlTool, WebSearchTool
from tools.xlsx_tools import (
    AddSpreadsheetChartTool,
    AddSpreadsheetRowTool,
    CreateSpreadsheetTool,
    ListSpreadsheetsTool,
    SetSpreadsheetFormulaTool,
)
from tools.youtube_transcript_tool import GetYoutubeTranscriptTool


def build_registry(memory: Memory, store: Store | None = None) -> ToolRegistry:
    store = store or Store()
    registry = ToolRegistry(on_failure=lambda name, error: store.log_failed_command(name, error))

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

    # Projects / milestones
    registry.register(CreateProjectTool(store))
    registry.register(AddMilestoneTool(store))
    registry.register(ListProjectMilestonesTool(store))
    registry.register(CompleteMilestoneTool(store))
    registry.register(ListProjectsTool(store))

    # Live info (no API key needed)
    registry.register(WeatherTool())
    registry.register(SunTimesTool())
    registry.register(WikipediaSummaryTool())
    registry.register(CurrencyConversionTool())
    registry.register(StockPriceTool())
    registry.register(NewsHeadlinesTool())
    registry.register(CryptoPriceTool())
    registry.register(DictionaryTool())
    registry.register(HistoricalWeatherTool())
    registry.register(ReadRssFeedTool())
    registry.register(RedditTopPostsTool())
    registry.register(LatestGithubReleaseTool())
    registry.register(RecentGithubCommitsTool())
    registry.register(GetYoutubeTranscriptTool())
    registry.register(GetLyricsTool())

    # Open web
    registry.register(WebSearchTool())
    registry.register(FetchWebpageTool())
    registry.register(ShortenUrlTool())
    registry.register(PublicIpTool())
    registry.register(CheckUptimeTool())
    registry.register(CheckMultipleUptimeTool())

    # Fun
    registry.register(CoinFlipTool())
    registry.register(RollDiceTool())
    registry.register(MagicEightBallTool())
    registry.register(RandomQuoteTool())
    registry.register(JokeTool())
    registry.register(GenerateAmbientSoundTool())

    # Utilities
    registry.register(CalculatorTool())
    registry.register(UnitConversionTool())
    registry.register(GeneratePasswordTool())
    registry.register(GenerateQrCodeTool())

    # Self-monitoring / system
    registry.register(SystemStatusTool())
    registry.register(ListFailedCommandsTool(store))
    registry.register(FindLargeFilesTool())
    registry.register(FindDuplicateFilesTool())
    registry.register(SummarizeDirectoryTool())
    registry.register(RunBackupTool())
    registry.register(NetworkSpeedTestTool())
    registry.register(EmergencyAlertTool())
    registry.register(EmergencyWipeTool())
    registry.register(ListProcessesTool())
    registry.register(SetProcessPriorityTool())
    registry.register(CheckDiskHealthTool())
    registry.register(ReadTextFileTool())
    registry.register(SecurityAuditCodeTool())
    registry.register(CheckDependencyVulnerabilitiesTool())
    registry.register(RunSqlQueryTool())
    registry.register(RunDeployCommandTool())
    registry.register(ListDeployCommandsTool())
    registry.register(CheckPasswordLeakedTool())
    registry.register(CheckEmailBreachedTool())

    # Reasoning / creativity / analysis
    registry.register(DelegateToSubagentTool())
    registry.register(GenerateChartTool())
    registry.register(AnalyzeImageTool())
    registry.register(GenerateFlashcardsTool())
    registry.register(GenerateQuizTool())

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
    registry.register(SetSpreadsheetFormulaTool(store))
    registry.register(AddSpreadsheetChartTool(store))
    registry.register(ListSpreadsheetsTool(store))
    registry.register(ReadPdfTool())
    registry.register(ReadWordDocumentTool())

    # Composite tools pull from whatever else got registered above
    registry.register(MorningBriefingTool(registry))
    registry.register(EveningDebriefTool(registry))
    registry.register(PrepareMeetingBriefingTool(registry))

    if config.sandbox_enabled:
        from tools.sandbox_tools import RunPythonSnippetTool

        registry.register(RunPythonSnippetTool())

    try:
        from core.vector_memory import VectorMemory
        from tools.semantic_memory_tool import IndexMemoryTool, SearchMemoryTool

        vector_memory = VectorMemory()
        registry.register(IndexMemoryTool(vector_memory))
        registry.register(SearchMemoryTool(vector_memory))
    except ImportError:
        pass  # sentence-transformers not installed; semantic memory tools stay disabled

    if config.google_credentials_path:
        try:
            from tools.calendar_tool import CreateEventTool, ListEventsTool
            from tools.gmail_tool import (
                GmailArchiveTool,
                GmailCreateDraftTool,
                GmailMarkReadTool,
                GmailReadTool,
                GmailSearchTool,
                GmailUnreadCountTool,
            )
            from tools.google_contacts_tool import AddContactTool, SearchContactsTool

            registry.register(GmailSearchTool())
            registry.register(GmailReadTool())
            registry.register(GmailCreateDraftTool())
            registry.register(GmailArchiveTool())
            registry.register(GmailMarkReadTool())
            registry.register(GmailUnreadCountTool())
            registry.register(ListEventsTool())
            registry.register(CreateEventTool())
            registry.register(SearchContactsTool())
            registry.register(AddContactTool())
        except ImportError:
            pass  # google-api-python-client not installed; Google tools stay disabled

    if config.caldav_url and config.caldav_username and config.caldav_password:
        try:
            from tools.caldav_tools import CreateCaldavEventTool, ListCaldavEventsTool

            registry.register(ListCaldavEventsTool())
            registry.register(CreateCaldavEventTool())
        except ImportError:
            pass  # caldav not installed; CalDAV tools stay disabled

    if config.todoist_api_token:
        from tools.todoist_tools import AddTodoistTaskTool, CompleteTodoistTaskTool, ListTodoistTasksTool

        registry.register(AddTodoistTaskTool())
        registry.register(ListTodoistTasksTool())
        registry.register(CompleteTodoistTaskTool())

    if config.obsidian_vault_path:
        from tools.obsidian_tools import AppendObsidianNoteTool, CreateObsidianNoteTool

        registry.register(CreateObsidianNoteTool())
        registry.register(AppendObsidianNoteTool())

    if config.tmdb_api_key:
        from tools.movies_tool import SearchMovieTool, UpcomingMoviesTool

        registry.register(UpcomingMoviesTool())
        registry.register(SearchMovieTool())

    if config.home_assistant_url and config.home_assistant_token:
        from tools.home_assistant_tool import CallServiceTool, ListDevicesTool

        registry.register(ListDevicesTool())
        registry.register(CallServiceTool())

    if config.spotify_client_id and config.spotify_client_secret:
        try:
            from tools.spotify_tools import (
                AddTracksToSpotifyPlaylistTool,
                CreateSpotifyPlaylistTool,
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
            registry.register(CreateSpotifyPlaylistTool())
            registry.register(AddTracksToSpotifyPlaylistTool())
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
