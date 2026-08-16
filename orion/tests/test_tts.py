"""Regression test for PiperSynthesizer.synthesize(): piper-tts >=1.6.0
replaced synthesize_stream_raw() (removed entirely) with synthesize(),
which yields one AudioChunk per sentence instead of raw bytes — this
broke voice replies with AttributeError until core/tts.py was updated to
use AudioChunk.audio_int16_bytes instead. Uses a fake piper.voice module
so this test doesn't need the real (large) piper-tts wheel installed.
"""
from __future__ import annotations

import asyncio
import dataclasses
import sys
import types

import pytest

from core.config import config as real_config
from core.tts import (
    EdgeTTSSynthesizer,
    PiperSynthesizer,
    _strip_markdown_for_speech,
    get_synthesizer,
    get_synthesizer_if_available,
)


class _FakeAudioChunk:
    def __init__(self, data: bytes):
        self.audio_int16_bytes = data


class _FakeVoiceConfig:
    sample_rate = 22050


class _FakePiperVoice:
    def __init__(self):
        self.config = _FakeVoiceConfig()
        self.synthesize_calls: list[str] = []

    @classmethod
    def load(cls, path):
        instance = cls()
        instance.loaded_from = path
        return instance

    def synthesize(self, text):
        self.synthesize_calls.append(text)
        # Real piper-tts yields one AudioChunk per sentence — simulate two.
        return [_FakeAudioChunk(b"chunk1-"), _FakeAudioChunk(b"chunk2")]


@pytest.fixture(autouse=True)
def fake_piper_voice_module(monkeypatch):
    fake_module = types.ModuleType("piper.voice")
    fake_module.PiperVoice = _FakePiperVoice
    monkeypatch.setitem(sys.modules, "piper.voice", fake_module)
    monkeypatch.setitem(sys.modules, "piper", types.ModuleType("piper"))
    yield


def test_synthesize_joins_audio_chunk_bytes():
    synth = PiperSynthesizer("fake/model.onnx")

    result = synth.synthesize("Bonjour, comment vas-tu ?")

    assert result == b"chunk1-chunk2"
    assert synth._voice.synthesize_calls == ["Bonjour, comment vas-tu ?"]


def test_synthesize_returns_bytes_not_audio_chunks():
    synth = PiperSynthesizer("fake/model.onnx")
    result = synth.synthesize("test")
    assert isinstance(result, bytes)


def test_sample_rate_comes_from_voice_config():
    synth = PiperSynthesizer("fake/model.onnx")
    assert synth.sample_rate == 22050


def test_voice_loaded_from_given_path():
    synth = PiperSynthesizer("some/path/fr_FR-siwis-medium.onnx")
    assert synth._voice.loaded_from == "some/path/fr_FR-siwis-medium.onnx"


def test_synthesize_skips_tts_entirely_for_pure_list_marker_fragment():
    """A sentence-splitter fragment that's nothing but a list marker (e.g.
    '1.' from a numbered list) strips down to empty — must not reach
    PiperVoice.synthesize() at all, since that's what caused it to be
    read aloud literally in the first place."""
    synth = PiperSynthesizer("fake/model.onnx")

    result = synth.synthesize("1.")

    assert result == b""
    assert synth._voice.synthesize_calls == []


# --- _strip_markdown_for_speech ---


def test_strips_numbered_list_markers():
    assert _strip_markdown_for_speech("1. Buy milk") == "Buy milk"


def test_strips_bullet_markers():
    assert _strip_markdown_for_speech("- Buy milk") == "Buy milk"
    assert _strip_markdown_for_speech("* Buy milk") == "Buy milk"


def test_strips_bold():
    assert _strip_markdown_for_speech("This is **important**.") == "This is important."


def test_strips_italic_without_breaking_bold():
    assert _strip_markdown_for_speech("This is *important*.") == "This is important."
    assert _strip_markdown_for_speech("**Bold** and *italic*.") == "Bold and italic."


def test_strips_inline_code():
    assert _strip_markdown_for_speech("Run `pip install`.") == "Run pip install."


def test_strips_markdown_headers():
    assert _strip_markdown_for_speech("## Summary") == "Summary"


def test_pure_list_marker_fragment_becomes_empty():
    assert _strip_markdown_for_speech("1.") == ""
    assert _strip_markdown_for_speech("2)") == ""


def test_leaves_plain_prose_untouched():
    text = "Bonjour ! Comment puis-je t'aider aujourd'hui ?"
    assert _strip_markdown_for_speech(text) == text


# --- unit normalization for speech (config.voice_language defaults to "fr") ---


def test_temperature_celsius_expands_to_the_full_word():
    assert _strip_markdown_for_speech("Il fait 23°C dehors.") == "Il fait 23 degrés Celsius dehors."


def test_temperature_fahrenheit_expands_to_the_full_word():
    assert _strip_markdown_for_speech("It's 70°F today.") == "It's 70 degrés Fahrenheit today."


def test_temperature_handles_decimal_and_negative_values():
    assert _strip_markdown_for_speech("-3.5°C") == "-3.5 degrés Celsius"


def test_percent_expands_to_the_full_word():
    assert _strip_markdown_for_speech("Humidité 82%") == "Humidité 82 pour cent"


def test_kmh_expands_to_the_full_phrase():
    assert _strip_markdown_for_speech("vent 12 km/h") == "vent 12 kilomètres par heure"


def test_currency_code_expands_to_the_full_word():
    assert _strip_markdown_for_speech("Bitcoin at 65000 USD") == "Bitcoin at 65000 dollars américains"
    assert _strip_markdown_for_speech("12.50 EUR") == "12.50 euros"
    assert _strip_markdown_for_speech("100 CHF") == "100 francs suisses"


def test_english_voice_language_uses_english_unit_words(monkeypatch):
    from core.config import config

    object.__setattr__(config, "voice_language", "en")
    try:
        assert _strip_markdown_for_speech("23°C, 80% humidity, 12 km/h") == (
            "23 degrees Celsius, 80 percent humidity, 12 kilometers per hour"
        )
        assert _strip_markdown_for_speech("100 USD") == "100 US dollars"
    finally:
        object.__setattr__(config, "voice_language", "fr")


def test_unit_normalization_does_not_touch_unrelated_numbers():
    assert _strip_markdown_for_speech("Reminder set for 15h.") == "Reminder set for 15h."


# --- EdgeTTSSynthesizer ---


class _FakeCommunicate:
    def __init__(self, text, voice):
        self.text = text
        self.voice = voice

    async def stream(self):
        yield {"type": "audio", "data": b"mp3-part1-"}
        yield {"type": "WordBoundary", "offset": 0, "duration": 1}  # non-audio events must be filtered out
        yield {"type": "audio", "data": b"mp3-part2"}


@pytest.fixture(autouse=True)
def fake_edge_tts_module(monkeypatch):
    fake_module = types.ModuleType("edge_tts")
    fake_module.Communicate = _FakeCommunicate
    monkeypatch.setitem(sys.modules, "edge_tts", fake_module)
    yield


@pytest.fixture(autouse=True)
def fake_ffmpeg(monkeypatch):
    calls = []

    def fake_run(cmd, input, stdout, stderr, check, timeout=None):
        calls.append({"cmd": cmd, "input": input, "timeout": timeout})
        return types.SimpleNamespace(stdout=b"pcm-bytes")

    monkeypatch.setattr("core.tts.subprocess.run", fake_run)
    return calls


def test_edge_tts_synthesize_joins_audio_chunks_and_decodes_via_ffmpeg(fake_ffmpeg):
    synth = EdgeTTSSynthesizer("fr-FR-HenriNeural")

    result = synth.synthesize("Bonjour")

    assert result == b"pcm-bytes"
    assert fake_ffmpeg[0]["input"] == b"mp3-part1-mp3-part2"
    assert "-ar" in fake_ffmpeg[0]["cmd"]


def test_edge_tts_ffmpeg_decode_has_a_timeout(fake_ffmpeg):
    """A truncated/corrupted mp3 stream (a network hiccup partway through
    edge-tts's response) used to be able to hang this ffmpeg call forever —
    with nothing upstream catching that, it could take down whichever
    always-on interface hit it. Regression test for the timeout= that
    closes that gap."""
    EdgeTTSSynthesizer("fr-FR-HenriNeural").synthesize("Bonjour")

    assert fake_ffmpeg[0]["timeout"] is not None
    assert fake_ffmpeg[0]["timeout"] > 0


def test_edge_tts_skips_ffmpeg_for_pure_list_marker_fragment(fake_ffmpeg):
    synth = EdgeTTSSynthesizer("fr-FR-HenriNeural")

    result = synth.synthesize("1.")

    assert result == b""
    assert fake_ffmpeg == []


def test_edge_tts_sample_rate_is_24000():
    assert EdgeTTSSynthesizer("fr-FR-HenriNeural").sample_rate == 24000


class _HangingCommunicate:
    """Simulates a stalled network connection to Edge TTS's endpoint (dead
    wifi, a DNS hiccup, the service just not responding) -- stream() never
    yields anything and never finishes on its own."""

    def __init__(self, text, voice):
        pass

    async def stream(self):
        await asyncio.sleep(3600)
        yield {"type": "audio", "data": b"unreachable"}  # pragma: no cover


def test_edge_tts_network_call_has_a_timeout(monkeypatch, fake_ffmpeg):
    """Regression test: confirmed live -- a stalled Edge TTS request used to
    hang here indefinitely with nothing bounding it, and because every
    Synthesizer.synthesize() caller is synchronous, that froze the entire
    always-on voice loop completely (it stopped responding to the wake word
    at all, since the one thread that needed to get back to listening for
    it was stuck in here instead). Patches the timeout down to keep this
    test itself fast rather than actually waiting out the real 15s one."""
    import core.tts as tts_module

    monkeypatch.setattr(tts_module, "_EDGE_TTS_NETWORK_TIMEOUT_S", 0.05)
    monkeypatch.setattr(sys.modules["edge_tts"], "Communicate", _HangingCommunicate)

    result = EdgeTTSSynthesizer("fr-FR-HenriNeural").synthesize("Bonjour")

    assert result == b""
    assert fake_ffmpeg == []  # never got far enough to even try decoding


# --- get_synthesizer / get_synthesizer_if_available selection chain ---


def test_get_synthesizer_prefers_elevenlabs_over_everything(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "elevenlabs.client",
        types.SimpleNamespace(ElevenLabs=lambda api_key, timeout=None: object()),
    )
    cfg = dataclasses.replace(real_config, elevenlabs_api_key="key123", edge_tts_voice="fr-FR-HenriNeural")
    monkeypatch.setattr("core.tts.config", cfg)

    synth = get_synthesizer("some/piper/model.onnx")

    assert type(synth).__name__ == "ElevenLabsSynthesizer"


def test_get_synthesizer_prefers_piper_over_edge_when_no_elevenlabs(monkeypatch):
    cfg = dataclasses.replace(real_config, elevenlabs_api_key=None, edge_tts_voice="fr-FR-HenriNeural")
    monkeypatch.setattr("core.tts.config", cfg)

    synth = get_synthesizer("fake/model.onnx")

    assert isinstance(synth, PiperSynthesizer)


def test_get_synthesizer_falls_back_to_edge_tts_with_no_piper_model(monkeypatch):
    cfg = dataclasses.replace(real_config, elevenlabs_api_key=None, edge_tts_voice="fr-FR-HenriNeural")
    monkeypatch.setattr("core.tts.config", cfg)

    synth = get_synthesizer(None)

    assert isinstance(synth, EdgeTTSSynthesizer)


def test_get_synthesizer_raises_a_clear_error_when_nothing_is_configured(monkeypatch):
    cfg = dataclasses.replace(real_config, elevenlabs_api_key=None, edge_tts_voice="")
    monkeypatch.setattr("core.tts.config", cfg)

    with pytest.raises(RuntimeError, match="No TTS backend available"):
        get_synthesizer(None)


def test_get_synthesizer_falls_back_to_edge_tts_when_edge_package_missing(monkeypatch):
    monkeypatch.delitem(sys.modules, "edge_tts", raising=False)
    monkeypatch.setitem(sys.modules, "edge_tts", None)  # forces ImportError on `import edge_tts`
    cfg = dataclasses.replace(real_config, elevenlabs_api_key=None, edge_tts_voice="fr-FR-HenriNeural")
    monkeypatch.setattr("core.tts.config", cfg)

    with pytest.raises(RuntimeError, match="No TTS backend available"):
        get_synthesizer(None)


def test_get_synthesizer_if_available_returns_none_instead_of_raising(monkeypatch):
    cfg = dataclasses.replace(real_config, elevenlabs_api_key=None, edge_tts_voice="")
    monkeypatch.setattr("core.tts.config", cfg)
    monkeypatch.setattr("core.tts.find_local_piper_model", lambda: None)

    assert get_synthesizer_if_available() is None


def test_get_synthesizer_if_available_returns_edge_tts_as_the_zero_setup_default(monkeypatch):
    cfg = dataclasses.replace(real_config, elevenlabs_api_key=None, edge_tts_voice="fr-FR-HenriNeural")
    monkeypatch.setattr("core.tts.config", cfg)
    monkeypatch.setattr("core.tts.find_local_piper_model", lambda: None)

    assert isinstance(get_synthesizer_if_available(), EdgeTTSSynthesizer)
