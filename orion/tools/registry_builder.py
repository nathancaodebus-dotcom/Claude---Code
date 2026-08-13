"""Assembles the ToolRegistry, enabling each integration only if it's configured
— and, just as importantly, tolerating any tool's dependency failing to
install at all (a real, recurring situation on Termux/Android, where many
PyPI packages have no prebuilt wheel and fail to build from source).

Every tool module is imported lazily, one small group at a time, through
_register_safe(): if that group's import raises ImportError (a missing
package), only that group is skipped — never the rest of the registry. This
is what makes 'add a new capability' a one-file change and 'a dependency
doesn't install on this platform' a one-feature loss instead of a crash.
"""
from __future__ import annotations

import logging

from core.config import config
from core.memory import Memory
from core.store import Store
from tools.base import ToolRegistry

logger = logging.getLogger("orion.registry")


def _register_safe(registry: ToolRegistry, label: str, register_fn) -> None:
    try:
        register_fn()
    except ImportError as exc:
        logger.warning("Skipping '%s' tools — missing dependency: %s", label, exc)


def build_registry(memory: Memory, store: Store | None = None) -> ToolRegistry:
    store = store or Store()
    registry = ToolRegistry(on_failure=lambda name, error: store.log_failed_command(name, error))

    # Memory — no third-party dependency, always available.
    from tools.memory_tool import RecallFactsTool, RememberFactTool

    registry.register(RememberFactTool(memory))
    registry.register(RecallFactsTool(memory))

    def _productivity() -> None:
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

    _register_safe(registry, "productivity", _productivity)

    def _projects() -> None:
        from tools.project_tools import (
            AddMilestoneTool,
            CompleteMilestoneTool,
            CreateProjectTool,
            ListProjectMilestonesTool,
            ListProjectsTool,
        )

        registry.register(CreateProjectTool(store))
        registry.register(AddMilestoneTool(store))
        registry.register(ListProjectMilestonesTool(store))
        registry.register(CompleteMilestoneTool(store))
        registry.register(ListProjectsTool(store))

    _register_safe(registry, "projects", _projects)

    def _live_info() -> None:
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

        registry.register(WeatherTool())
        registry.register(SunTimesTool())
        registry.register(WikipediaSummaryTool())
        registry.register(CurrencyConversionTool())
        registry.register(StockPriceTool())
        registry.register(NewsHeadlinesTool())
        registry.register(CryptoPriceTool())
        registry.register(DictionaryTool())
        registry.register(HistoricalWeatherTool())

    _register_safe(registry, "live info", _live_info)

    def _crypto_trading() -> None:
        from tools.crypto_tools import (
            CompareCryptoAssetsTool,
            ConfirmCryptoTradeTool,
            GetCryptoMarketDataTool,
            GetCryptoTechnicalIndicatorsTool,
            ListCryptoHoldingsTool,
            ListPendingCryptoTradesTool,
            ProposeCryptoTradeTool,
            RejectCryptoTradeTool,
            SuggestPositionSizeTool,
        )

        registry.register(GetCryptoMarketDataTool())
        registry.register(CompareCryptoAssetsTool())
        registry.register(GetCryptoTechnicalIndicatorsTool())
        registry.register(ProposeCryptoTradeTool(store))
        registry.register(ConfirmCryptoTradeTool(store))
        registry.register(RejectCryptoTradeTool(store))
        registry.register(ListPendingCryptoTradesTool(store))
        registry.register(ListCryptoHoldingsTool(store))
        registry.register(SuggestPositionSizeTool())

    _register_safe(registry, "crypto trading (research + paper portfolio)", _crypto_trading)

    def _quant_signals() -> None:
        from tools.quant_signal_tools import BacktestQuantSignalTool, ListQuantSignalsTool, SaveQuantSignalTool

        registry.register(BacktestQuantSignalTool())
        registry.register(SaveQuantSignalTool(store))
        registry.register(ListQuantSignalsTool(store))

    _register_safe(registry, "quantitative signal research", _quant_signals)

    def _rss_reddit() -> None:
        from tools.rss_reddit_tools import ReadRssFeedTool, RedditTopPostsTool

        registry.register(ReadRssFeedTool())
        registry.register(RedditTopPostsTool())

    _register_safe(registry, "RSS/Reddit", _rss_reddit)

    def _github_watch() -> None:
        from tools.github_watch_tools import LatestGithubReleaseTool, RecentGithubCommitsTool

        registry.register(LatestGithubReleaseTool())
        registry.register(RecentGithubCommitsTool())

    _register_safe(registry, "GitHub watch", _github_watch)

    def _youtube_transcript() -> None:
        from tools.youtube_transcript_tool import GetYoutubeTranscriptTool

        registry.register(GetYoutubeTranscriptTool())

    _register_safe(registry, "YouTube transcript", _youtube_transcript)

    def _lyrics() -> None:
        from tools.lyrics_tool import GetLyricsTool

        registry.register(GetLyricsTool())

    _register_safe(registry, "lyrics", _lyrics)

    def _web() -> None:
        from tools.web_tools import FetchWebpageTool, PublicIpTool, ShortenUrlTool, WebSearchTool

        registry.register(WebSearchTool())
        registry.register(FetchWebpageTool())
        registry.register(ShortenUrlTool())
        registry.register(PublicIpTool())

    _register_safe(registry, "web", _web)

    def _uptime() -> None:
        from tools.uptime_monitor_tool import CheckMultipleUptimeTool, CheckUptimeTool

        registry.register(CheckUptimeTool())
        registry.register(CheckMultipleUptimeTool())

    _register_safe(registry, "uptime monitor", _uptime)

    def _fun() -> None:
        from tools.fun_tools import CoinFlipTool, JokeTool, MagicEightBallTool, RandomQuoteTool, RollDiceTool

        registry.register(CoinFlipTool())
        registry.register(RollDiceTool())
        registry.register(MagicEightBallTool())
        registry.register(RandomQuoteTool())
        registry.register(JokeTool())

    _register_safe(registry, "fun", _fun)

    def _ambient_sound() -> None:
        # Needs numpy, which has no prebuilt wheel on Termux/Android.
        from tools.ambient_sound_tool import GenerateAmbientSoundTool

        registry.register(GenerateAmbientSoundTool())

    _register_safe(registry, "ambient sound", _ambient_sound)

    def _utilities() -> None:
        # qrcode[pil] pulls in Pillow, which can fail to build on some
        # platforms without system jpeg/zlib headers.
        from tools.utility_tools import CalculatorTool, GeneratePasswordTool, GenerateQrCodeTool, UnitConversionTool

        registry.register(CalculatorTool())
        registry.register(UnitConversionTool())
        registry.register(GeneratePasswordTool())
        registry.register(GenerateQrCodeTool())

    _register_safe(registry, "utilities", _utilities)

    def _system() -> None:
        # tools/system_tool.py itself degrades gracefully without psutil
        # (Android hard-refuses it) — this import always succeeds.
        from tools.system_tool import (
            ListFailedCommandsTool,
            ListProcessesTool,
            SetProcessPriorityTool,
            SystemStatusTool,
        )

        registry.register(SystemStatusTool())
        registry.register(ListFailedCommandsTool(store))
        registry.register(ListProcessesTool())
        registry.register(SetProcessPriorityTool())

    _register_safe(registry, "system", _system)

    def _file_manager() -> None:
        from tools.file_manager_tools import FindDuplicateFilesTool, FindLargeFilesTool, SummarizeDirectoryTool

        registry.register(FindLargeFilesTool())
        registry.register(FindDuplicateFilesTool())
        registry.register(SummarizeDirectoryTool())

    _register_safe(registry, "file manager", _file_manager)

    def _backup() -> None:
        from tools.backup_tools import RunBackupTool

        registry.register(RunBackupTool())

    _register_safe(registry, "backup", _backup)

    def _network_speed() -> None:
        from tools.network_tools import NetworkSpeedTestTool

        registry.register(NetworkSpeedTestTool())

    _register_safe(registry, "network speed test", _network_speed)

    def _emergency() -> None:
        from tools.emergency_tool import EmergencyAlertTool

        registry.register(EmergencyAlertTool())

    _register_safe(registry, "emergency alert", _emergency)

    def _kill_switch() -> None:
        from tools.killswitch_tool import EmergencyWipeTool

        registry.register(EmergencyWipeTool())

    _register_safe(registry, "kill switch", _kill_switch)

    def _disk_health() -> None:
        from tools.disk_health_tool import CheckDiskHealthTool

        registry.register(CheckDiskHealthTool())

    _register_safe(registry, "disk health", _disk_health)

    def _text_file() -> None:
        from tools.text_file_tool import ReadTextFileTool

        registry.register(ReadTextFileTool())

    _register_safe(registry, "text file reader", _text_file)

    def _security_audit() -> None:
        from tools.security_audit_tools import CheckDependencyVulnerabilitiesTool, SecurityAuditCodeTool

        registry.register(SecurityAuditCodeTool())
        registry.register(CheckDependencyVulnerabilitiesTool())

    _register_safe(registry, "security audit", _security_audit)

    def _sql() -> None:
        from tools.sql_tool import RunSqlQueryTool

        registry.register(RunSqlQueryTool())

    _register_safe(registry, "SQL", _sql)

    def _deploy() -> None:
        from tools.deploy_tool import ListDeployCommandsTool, RunDeployCommandTool

        registry.register(RunDeployCommandTool())
        registry.register(ListDeployCommandsTool())

    _register_safe(registry, "deploy commands", _deploy)

    def _leak_check() -> None:
        from tools.leak_check_tool import CheckEmailBreachedTool, CheckPasswordLeakedTool

        registry.register(CheckPasswordLeakedTool())
        registry.register(CheckEmailBreachedTool())

    _register_safe(registry, "credential leak check", _leak_check)

    def _subagent() -> None:
        from tools.subagent_tool import DelegateToSubagentTool

        registry.register(DelegateToSubagentTool())

    _register_safe(registry, "sub-agent delegation", _subagent)

    def _chart() -> None:
        from tools.chart_tool import GenerateChartTool

        registry.register(GenerateChartTool())

    _register_safe(registry, "chart generation", _chart)

    def _image_analysis() -> None:
        from tools.image_analysis_tool import AnalyzeImageTool

        registry.register(AnalyzeImageTool())

    _register_safe(registry, "image analysis", _image_analysis)

    def _image_edit() -> None:
        # tools/image_edit_tools.py itself degrades gracefully without
        # Pillow (can fail to build without system jpeg/zlib headers) —
        # this import always succeeds.
        from tools.image_edit_tools import AddTextToImageTool, CreateImageCollageTool, EditImageTool

        registry.register(EditImageTool())
        registry.register(AddTextToImageTool())
        registry.register(CreateImageCollageTool())

    _register_safe(registry, "image editing", _image_edit)

    def _video_edit() -> None:
        from tools.video_edit_tools import (
            AddAudioToVideoTool,
            AddCaptionToVideoTool,
            AddWatermarkToVideoTool,
            ChangeVideoSpeedTool,
            ConcatenateVideosTool,
            ConvertVideoFormatTool,
            ExtractAudioFromVideoTool,
            ExtractVideoFrameTool,
            TrimVideoTool,
        )

        registry.register(TrimVideoTool())
        registry.register(ConcatenateVideosTool())
        registry.register(ExtractAudioFromVideoTool())
        registry.register(AddAudioToVideoTool())
        registry.register(ConvertVideoFormatTool())
        registry.register(AddCaptionToVideoTool())
        registry.register(AddWatermarkToVideoTool())
        registry.register(ChangeVideoSpeedTool())
        registry.register(ExtractVideoFrameTool())

    _register_safe(registry, "video editing", _video_edit)

    def _flashcards() -> None:
        from tools.flashcard_tool import GenerateClozeFlashcardsTool, GenerateFlashcardsTool, GenerateQuizTool

        registry.register(GenerateFlashcardsTool())
        registry.register(GenerateClozeFlashcardsTool())
        registry.register(GenerateQuizTool())

    _register_safe(registry, "flashcards/quiz", _flashcards)

    def _pptx() -> None:
        from tools.pptx_tools import (
            AddImageToSlideTool,
            AddSlideTool,
            CreatePresentationTool,
            DeleteSlideTool,
            EditSlideTool,
            ListPresentationsTool,
            ListSlidesTool,
            SetSlideNotesTool,
        )

        registry.register(CreatePresentationTool(store))
        registry.register(AddSlideTool(store))
        registry.register(EditSlideTool(store))
        registry.register(DeleteSlideTool(store))
        registry.register(ListSlidesTool(store))
        registry.register(ListPresentationsTool(store))
        registry.register(AddImageToSlideTool(store))
        registry.register(SetSlideNotesTool(store))

    _register_safe(registry, "PowerPoint", _pptx)

    def _website() -> None:
        from tools.website_tools import (
            AddWebsiteImageTool,
            AddWebsitePageTool,
            CreateWebsiteTool,
            DeleteWebsitePageTool,
            EditWebsitePageTool,
            ListWebsitePagesTool,
            ListWebsitesTool,
        )

        registry.register(CreateWebsiteTool(store))
        registry.register(AddWebsitePageTool(store))
        registry.register(EditWebsitePageTool(store))
        registry.register(DeleteWebsitePageTool(store))
        registry.register(ListWebsitePagesTool(store))
        registry.register(ListWebsitesTool(store))
        registry.register(AddWebsiteImageTool(store))

    _register_safe(registry, "website creation", _website)

    if config.github_pages_token and config.github_pages_owner:
        def _website_publish() -> None:
            from tools.website_publish_tools import PublishWebsiteToGithubPagesTool

            registry.register(PublishWebsiteToGithubPagesTool(store))

        _register_safe(registry, "website publishing (GitHub Pages)", _website_publish)

    if config.infomaniak_ftp_host and config.infomaniak_ftp_username and config.infomaniak_ftp_password:
        def _website_publish_infomaniak() -> None:
            # tools/website_publish_tools.py itself degrades gracefully
            # without paramiko (Rust-adjacent cryptography dependency,
            # slow/fragile to build on Termux) — this import always succeeds.
            from tools.website_publish_tools import PublishWebsiteToInfomaniakTool

            registry.register(PublishWebsiteToInfomaniakTool(store))

        _register_safe(registry, "website publishing (Infomaniak)", _website_publish_infomaniak)

    def _docx() -> None:
        from tools.docx_tools import (
            AddImageToWordDocumentTool,
            AddTableToWordDocumentTool,
            AppendToWordDocumentTool,
            CreateWordDocumentTool,
            ListWordDocumentsTool,
        )

        registry.register(CreateWordDocumentTool(store))
        registry.register(AppendToWordDocumentTool(store))
        registry.register(ListWordDocumentsTool(store))
        registry.register(AddTableToWordDocumentTool(store))
        registry.register(AddImageToWordDocumentTool(store))

    _register_safe(registry, "Word", _docx)

    def _xlsx() -> None:
        from tools.xlsx_tools import (
            AddSpreadsheetChartTool,
            AddSpreadsheetRowTool,
            AddSpreadsheetSheetTool,
            CreateSpreadsheetTool,
            FormatSpreadsheetCellsTool,
            ListSpreadsheetsTool,
            SetSpreadsheetFormulaTool,
        )

        registry.register(CreateSpreadsheetTool(store))
        registry.register(AddSpreadsheetRowTool(store))
        registry.register(SetSpreadsheetFormulaTool(store))
        registry.register(AddSpreadsheetChartTool(store))
        registry.register(ListSpreadsheetsTool(store))
        registry.register(FormatSpreadsheetCellsTool(store))
        registry.register(AddSpreadsheetSheetTool(store))

    _register_safe(registry, "Excel", _xlsx)

    def _document_readers() -> None:
        from tools.document_reader_tools import ReadPdfTool, ReadWordDocumentTool

        registry.register(ReadPdfTool())
        registry.register(ReadWordDocumentTool())

    _register_safe(registry, "document readers", _document_readers)

    def _briefings() -> None:
        from tools.briefing_tools import EveningDebriefTool, MorningBriefingTool
        from tools.meeting_briefing_tool import PrepareMeetingBriefingTool

        # These pull from whatever else got registered above, so register
        # them last regardless of which other groups succeeded.
        registry.register(MorningBriefingTool(registry))
        registry.register(EveningDebriefTool(registry))
        registry.register(PrepareMeetingBriefingTool(registry))

    _register_safe(registry, "briefings", _briefings)

    if config.sandbox_enabled:
        def _sandbox() -> None:
            from tools.sandbox_tools import RunPythonSnippetTool

            registry.register(RunPythonSnippetTool())

        _register_safe(registry, "sandboxed scripts", _sandbox)

    def _semantic_memory() -> None:
        from core.vector_memory import VectorMemory
        from tools.semantic_memory_tool import IndexMemoryTool, SearchMemoryTool

        vector_memory = VectorMemory()
        registry.register(IndexMemoryTool(vector_memory))
        registry.register(SearchMemoryTool(vector_memory))

    _register_safe(registry, "semantic memory", _semantic_memory)

    if config.google_credentials_path:
        def _google() -> None:
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

        _register_safe(registry, "Google (Gmail/Calendar/Contacts)", _google)

    if config.microsoft_client_id:
        def _microsoft() -> None:
            from tools.microsoft_calendar_tool import CreateOutlookEventTool, ListOutlookEventsTool
            from tools.microsoft_contacts_tool import AddOutlookContactTool, SearchOutlookContactsTool
            from tools.outlook_tool import (
                OutlookArchiveTool,
                OutlookCreateDraftTool,
                OutlookMarkReadTool,
                OutlookReadTool,
                OutlookSearchTool,
                OutlookUnreadCountTool,
            )

            registry.register(OutlookSearchTool())
            registry.register(OutlookReadTool())
            registry.register(OutlookCreateDraftTool())
            registry.register(OutlookArchiveTool())
            registry.register(OutlookMarkReadTool())
            registry.register(OutlookUnreadCountTool())
            registry.register(ListOutlookEventsTool())
            registry.register(CreateOutlookEventTool())
            registry.register(SearchOutlookContactsTool())
            registry.register(AddOutlookContactTool())

        _register_safe(registry, "Microsoft 365 (Outlook Mail/Calendar/Contacts)", _microsoft)

    if config.shopify_store_domain and config.shopify_access_token:
        def _shopify() -> None:
            from tools.shopify_tools import (
                CreateShopifyDiscountTool,
                CreateShopifyProductTool,
                FulfillShopifyOrderTool,
                GetShopifyCustomerOrdersTool,
                GetShopifyOrderTool,
                GetShopifyProductTool,
                GetShopifySalesSummaryTool,
                ListShopifyOrdersTool,
                ListShopifyProductsTool,
                SearchShopifyCustomersTool,
                UpdateShopifyInventoryTool,
                UpdateShopifyProductTool,
            )

            registry.register(ListShopifyOrdersTool())
            registry.register(GetShopifyOrderTool())
            registry.register(FulfillShopifyOrderTool())
            registry.register(GetShopifySalesSummaryTool())
            registry.register(ListShopifyProductsTool())
            registry.register(GetShopifyProductTool())
            registry.register(CreateShopifyProductTool())
            registry.register(UpdateShopifyProductTool())
            registry.register(UpdateShopifyInventoryTool())
            registry.register(SearchShopifyCustomersTool())
            registry.register(GetShopifyCustomerOrdersTool())
            registry.register(CreateShopifyDiscountTool())

        _register_safe(registry, "Shopify (e-commerce)", _shopify)

    if config.gemini_api_key:
        def _image_gen() -> None:
            from tools.image_gen_tools import GenerateImageTool

            registry.register(GenerateImageTool())

        _register_safe(registry, "image generation (Gemini)", _image_gen)

    if config.caldav_url and config.caldav_username and config.caldav_password:
        def _caldav() -> None:
            from tools.caldav_tools import CreateCaldavEventTool, ListCaldavEventsTool

            registry.register(ListCaldavEventsTool())
            registry.register(CreateCaldavEventTool())

        _register_safe(registry, "CalDAV", _caldav)

    if config.todoist_api_token:
        def _todoist() -> None:
            from tools.todoist_tools import AddTodoistTaskTool, CompleteTodoistTaskTool, ListTodoistTasksTool

            registry.register(AddTodoistTaskTool())
            registry.register(ListTodoistTasksTool())
            registry.register(CompleteTodoistTaskTool())

        _register_safe(registry, "Todoist", _todoist)

    if config.obsidian_vault_path:
        def _obsidian() -> None:
            from tools.obsidian_tools import AppendObsidianNoteTool, CreateObsidianNoteTool, ListObsidianNotesTool

            registry.register(CreateObsidianNoteTool())
            registry.register(AppendObsidianNoteTool())
            registry.register(ListObsidianNotesTool())

        _register_safe(registry, "Obsidian", _obsidian)

    if config.tmdb_api_key:
        def _tmdb() -> None:
            from tools.movies_tool import SearchMovieTool, UpcomingMoviesTool

            registry.register(UpcomingMoviesTool())
            registry.register(SearchMovieTool())

        _register_safe(registry, "TMDb", _tmdb)

    if config.home_assistant_url and config.home_assistant_token:
        def _home_assistant() -> None:
            from tools.home_assistant_tool import CallServiceTool, ListDevicesTool

            registry.register(ListDevicesTool())
            registry.register(CallServiceTool())

        _register_safe(registry, "Home Assistant", _home_assistant)

    if config.spotify_client_id and config.spotify_client_secret:
        def _spotify() -> None:
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

        _register_safe(registry, "Spotify", _spotify)

    def _casting() -> None:
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

    _register_safe(registry, "Chromecast/YouTube casting", _casting)

    return registry
