"""Per-query tool relevance filtering: shrinks the tool schema list Claude
sees on a turn's first API call instead of always sending the full
registry, inspired by isair/jarvis's tools/selection.py -- specifically its
"keyword" strategy. Its embedding/LLM strategies were deliberately not
ported: both add a network call of their own before the real request can
even start, which would fight the "faster" goal this exists to serve.
Pure local string matching costs microseconds, not a round trip.

Orion's registry has grown past 150 tools (core/agent.py, MCP, browser
automation, ...its own JSON schema is ~15K tokens serialized) — sent in
full on every Claude call regardless of whether the query needs any tool
at all. Prompt caching (core/agent.py's cache_control on the schema list)
already amortizes this *within* a burst of consecutive turns, but Anthropic's
ephemeral cache has a 5-minute TTL: a personal assistant asked something
once every 10-20 minutes, which is Orion's normal usage pattern, is an
uncached call most of the time regardless of caching. Shrinking the actual
payload is what helps that common case.

Bilingual matching, unlike the source project's English-only version:
Orion's tools are named/described in English, but its actual user writes in
French. Naively tokenizing a French query and overlapping it against English
tool vocabulary would silently match almost nothing ("météo" has zero
token overlap with "weather"), which would make the filter actively harmful
-- it would hide the very tool a French query needed. _FR_TO_EN_ALIASES is a
bounded, hand-curated translation layer covering Orion's actual tool
domains: unmapped French words simply don't expand, which is fine, because
the fallback below (too few tools matched -> return everything unfiltered)
makes an incomplete dictionary a lost optimization, never a lost tool.

Safety net, matching the source project's own conservative design: filtering
only activates when the registry is large enough to be worth the risk
(_MIN_TOOLS_TO_BOTHER) and only when enough *distinct* tools keyword-matched
to trust the result (_MIN_MATCHED_TOOLS) -- otherwise this returns every
tool, exactly today's unfiltered behavior. A query that matches nothing is
far more likely to be a genuinely tool-agnostic question ("what's 12*7") than
proof every one of 150+ tools is irrelevant, so the ambiguous case defaults
to "keep everything" rather than risk hiding something Claude actually needs.

core/agent.py additionally applies this only to iteration 0 of a turn's
tool-use loop -- if the loop is still running after that (Claude asked for a
tool, and then another), every later call reverts to the full, unfiltered
registry. A one-shot read of the user's opening message is a reasonable
guess at what a *single* tool call needs; trusting it for an unpredictable
chain of *further* tool calls is not, the same reasoning
ROUTING_ESCALATION_ITERATION already applies to model selection.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.base import Tool

# Below this many tools, the full registry is already small/cheap enough
# that filtering isn't worth its own complexity or false-negative risk.
_MIN_TOOLS_TO_BOTHER = 30
# If keyword matching finds fewer than this many distinct tools, treat the
# match as too sparse to trust -- send everything instead (today's baseline
# behavior), rather than risk narrowing to a handful of wrong guesses.
_MIN_MATCHED_TOOLS = 6

_TOKEN_RE = re.compile(r"[a-zà-öø-ÿ0-9]+")

_STOP_WORDS = frozenset({
    # English
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "i", "me", "my",
    "you", "your", "he", "she", "it", "we", "they", "them", "this",
    "that", "what", "which", "who", "when", "where", "how", "not", "no",
    "so", "if", "or", "and", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "into", "about", "up", "out",
    "off", "over", "just", "also", "very", "too", "some", "any", "all",
    # French
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "est",
    "es", "suis", "sont", "que", "qui", "quoi", "comment", "pourquoi",
    "quand", "où", "je", "tu", "il", "elle", "nous", "vous", "ils",
    "elles", "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses",
    "ce", "cette", "ces", "pour", "avec", "sans", "dans", "sur", "sous",
    "par", "au", "aux", "peux", "peut", "veux", "veut", "faire", "fait",
    "pas", "plus", "très", "aussi", "tout", "toute", "tous", "toutes",
    "s'il", "te", "moi", "stp",
})

# Bounded French -> English translation layer for Orion's actual tool
# domains (see module docstring for why this exists and why an incomplete
# list here is safe rather than silently broken). Grouped by the tool
# groups they map onto in tools/registry_builder.py; a French word not
# listed here just doesn't expand, which the fallback in select_relevant_
# tools() covers.
_FR_TO_EN_ALIASES: dict[str, str] = {
    # weather
    "météo": "weather", "temps": "weather", "température": "temperature",
    "pluie": "rain", "neige": "snow", "prévision": "forecast",
    "prévisions": "forecast", "demain": "tomorrow", "vent": "wind",
    # email
    "courriel": "email", "courriels": "email", "mail": "email",
    "mails": "email", "boîte": "inbox", "brouillon": "draft",
    # calendar
    "agenda": "calendar", "calendrier": "calendar", "rendez-vous": "event",
    "réunion": "meeting", "événement": "event",
    # home automation
    "domotique": "home", "maison": "home", "lumière": "light",
    "lumières": "light", "chauffage": "heating", "allume": "turn on",
    "éteins": "turn off",
    # music / casting
    "musique": "music", "chanson": "song", "morceau": "track",
    "vidéo": "video", "regarder": "watch", "télé": "tv",
    "télévision": "tv",
    # productivity
    "tâche": "task", "tâches": "task", "liste": "list", "note": "note",
    "notes": "note", "courses": "shopping", "achats": "shopping",
    "rappel": "reminder", "rappels": "reminder", "minuteur": "timer",
    "alarme": "alarm", "projet": "project", "étape": "milestone",
    # crypto / finance
    "crypto": "crypto", "monnaie": "currency", "portefeuille": "wallet",
    "action": "stock", "actions": "stock", "bourse": "stock",
    "devise": "currency", "change": "exchange", "prix": "price",
    # documents
    "document": "document", "présentation": "presentation",
    "diapositive": "slide", "tableau": "spreadsheet",
    "feuille": "spreadsheet", "classeur": "spreadsheet",
    # web / site / images / video
    "site": "website", "page": "page", "recherche": "search",
    "cherche": "search", "image": "image", "photo": "image",
    "montage": "edit", "navigateur": "browser",
    # system / security / network
    "système": "system", "batterie": "battery", "sécurité": "security",
    "mot": "word", "sauvegarde": "backup", "réseau": "network",
    "vitesse": "speed", "disque": "disk", "santé": "health",
    # misc info
    "actualité": "news", "actualités": "news", "nouvelles": "news",
    "film": "movie", "films": "movie", "dictionnaire": "dictionary",
    "définition": "definition", "contact": "contact", "contacts": "contact",
    "traduis": "translate", "traduction": "translate",
    "blague": "joke", "blagues": "joke", "citation": "quote",
    "dé": "dice", "dés": "dice", "pile": "flip",
    # deploy / dev
    "déploiement": "deploy", "déployer": "deploy", "dépôt": "repository",
}


def _tokenize(text: str) -> set[str]:
    # len() >= 2 discards single-character fragments -- English contractions
    # ("what's", "user's", "don't") are extremely common in this codebase's
    # tool descriptions, and _TOKEN_RE has no apostrophe in its character
    # class, so every one of them splits into a real word plus a bare "s" or
    # "t". Keeping those 1-char fragments as keywords made them near-
    # universal noise tokens -- almost every tool's description contains a
    # possessive somewhere, so a query containing so much as "what's" ended
    # up keyword-matching half the registry regardless of actual topic
    # (caught by testing this against the real ~150-tool registry, not just
    # small synthetic test fixtures).
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 2 and t not in _STOP_WORDS}


def _tokenize_with_aliases(text: str) -> set[str]:
    tokens = _tokenize(text)
    aliased = {_FR_TO_EN_ALIASES[t] for t in tokens if t in _FR_TO_EN_ALIASES}
    return tokens | aliased


@lru_cache(maxsize=512)
def _tool_keywords_cached(name: str, description: str) -> frozenset[str]:
    # A tool's name/description never changes for the life of the process
    # (found during a full-codebase audit: select_relevant_tools() re-ran
    # this tokenization from scratch for all 150+ tools on every single
    # turn -- pure repeated work). Cached by (name, description) rather
    # than the Tool object itself so it stays correct even if two Tool
    # instances happen to share a name/description (e.g. across tests),
    # and doesn't need Tool to be hashable.
    name_tokens = {t for t in name.split("_") if len(t) >= 2}
    return frozenset(name_tokens | _tokenize(description))


def _tool_keywords(tool: "Tool") -> frozenset[str]:
    return _tool_keywords_cached(tool.name, tool.description)


def select_relevant_tools(query: str, tools: list["Tool"]) -> list["Tool"]:
    """Returns the subset of *tools* whose name/description keywords
    overlap with *query* -- or every tool in *tools*, unchanged, whenever
    the registry is small or the match is too sparse to trust (see module
    docstring). Never raises, never returns an empty list when *tools*
    isn't empty."""
    if len(tools) < _MIN_TOOLS_TO_BOTHER:
        return tools

    query_tokens = _tokenize_with_aliases(query)
    if not query_tokens:
        return tools

    matched = [t for t in tools if query_tokens & _tool_keywords(t)]
    if len(matched) < _MIN_MATCHED_TOOLS:
        return tools
    return matched
