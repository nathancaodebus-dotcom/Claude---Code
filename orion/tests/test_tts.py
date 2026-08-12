"""Regression test for PiperSynthesizer.synthesize(): piper-tts >=1.6.0
replaced synthesize_stream_raw() (removed entirely) with synthesize(),
which yields one AudioChunk per sentence instead of raw bytes — this
broke voice replies with AttributeError until core/tts.py was updated to
use AudioChunk.audio_int16_bytes instead. Uses a fake piper.voice module
so this test doesn't need the real (large) piper-tts wheel installed.
"""
from __future__ import annotations

import sys
import types

import pytest

from core.tts import PiperSynthesizer, _strip_markdown_for_speech


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
