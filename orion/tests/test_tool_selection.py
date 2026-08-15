"""core/tool_selection.py's per-query keyword filtering -- ported from
isair/jarvis's tools/selection.py "keyword" strategy, adapted for Orion's
bilingual (French + English) user base. See that module's docstring for
the full design rationale (why keyword-only, why a French alias layer, why
the sparse-match fallback exists)."""
from __future__ import annotations

from core.tool_selection import select_relevant_tools


class _FakeTool:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description


# Two clusters of 7 tools each (above _MIN_MATCHED_TOOLS=6, mirroring how
# Orion's real registry has several Gmail/weather/etc. tools sharing the
# same domain keywords, not just one tool per domain) plus filler tools
# that share no keywords with either cluster, so exclusion assertions mean
# something.
_WEATHER_TOOLS = [
    ("get_weather", "Get the current weather forecast for a city."),
    ("get_historical_weather", "Compare today's weather to historical averages."),
    ("get_sun_times", "Get sunrise and sunset times for a weather location."),
    ("check_weather_alert", "Check for severe weather alerts in a region."),
    ("get_weather_radar", "Fetch a weather radar image for a city."),
    ("get_uv_index", "Get today's weather UV index forecast."),
    ("get_wind_speed", "Get the current weather wind speed for a city."),
]
_EMAIL_TOOLS = [
    ("send_gmail", "Send an email via Gmail."),
    ("search_gmail", "Search Gmail email messages."),
    ("read_gmail", "Read an email message from Gmail."),
    ("archive_gmail", "Archive an email message in Gmail."),
    ("mark_gmail_read", "Mark an email message as read in Gmail."),
    ("gmail_unread_count", "Count unread email messages in Gmail."),
    ("gmail_create_draft", "Create a draft email message in Gmail."),
]


def _make_tools(n: int) -> list[_FakeTool]:
    tools = [_FakeTool(name, desc) for name, desc in _WEATHER_TOOLS + _EMAIL_TOOLS]
    for i in range(max(0, n - len(tools))):
        tools.append(
            _FakeTool(f"filler_tool_{i}", f"Placeholder capability number {i} for testing purposes.")
        )
    return tools


def test_registry_below_threshold_is_never_filtered():
    tools = _make_tools(10)
    assert len(tools) < 30

    result = select_relevant_tools("what's the weather", tools)

    assert result == tools


def test_english_query_matches_the_right_cluster_in_a_large_registry():
    tools = _make_tools(40)

    result = select_relevant_tools("what's the weather like today", tools)

    names = {t.name for t in result}
    assert "get_weather" in names
    assert "send_gmail" not in names
    assert "filler_tool_0" not in names
    assert len(result) < len(tools)


def test_french_query_matches_via_the_alias_layer():
    tools = _make_tools(40)

    result = select_relevant_tools("quelle est la météo aujourd'hui", tools)

    names = {t.name for t in result}
    assert "get_weather" in names
    assert "send_gmail" not in names


def test_french_email_query_matches_via_the_alias_layer():
    tools = _make_tools(40)

    result = select_relevant_tools("envoie un courriel à Marie", tools)

    names = {t.name for t in result}
    assert "send_gmail" in names
    assert "get_weather" not in names


def test_empty_query_returns_everything_unfiltered():
    tools = _make_tools(40)

    result = select_relevant_tools("", tools)

    assert result == tools


def test_query_matching_nothing_falls_back_to_everything():
    tools = _make_tools(40)

    result = select_relevant_tools("xyzzyplugh qwertyuiop", tools)

    assert result == tools


def test_sparse_match_below_min_matched_falls_back_to_everything():
    """"sunset" only overlaps get_sun_times' own keywords -- one match,
    well under _MIN_MATCHED_TOOLS -- so this must fall back to sending
    every tool rather than narrowing to that single guess."""
    tools = _make_tools(40)

    result = select_relevant_tools("what time is sunset", tools)

    assert result == tools


def test_contractions_do_not_leak_single_letter_noise_tokens():
    """Regression test for a real bug caught by running this against
    Orion's actual ~150-tool registry (not just this file's small synthetic
    fixtures): "what's"/"user's"/"don't"-style contractions split into a
    real word plus a bare "s"/"t" fragment, since the tokenizer regex has
    no apostrophe in its character class. Almost every tool description in
    this codebase contains a possessive somewhere, so that bare "s" alone
    used to keyword-match roughly half the registry regardless of topic.
    Single-character tokens must never survive tokenization."""
    tools = _make_tools(40)

    result = select_relevant_tools("what's the weather like today", tools)

    names = {t.name for t in result}
    assert "get_weather" in names
    for name, _ in _EMAIL_TOOLS:
        assert name not in names
    assert not any(name.startswith("filler_tool_") for name in names)


def test_never_returns_an_empty_list_for_a_nonempty_registry():
    tools = _make_tools(40)
    for query in ("", "weather", "asdkjfhaskjdfh", "météo courriel calendrier"):
        assert len(select_relevant_tools(query, tools)) > 0
