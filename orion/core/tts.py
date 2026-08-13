"""Pluggable text-to-speech backend for the voice interface: Piper (local,
fully offline, but needs a voice model file downloaded once — see README §7
for the exact friction that step caused on a fresh Windows setup), ElevenLabs
(cloud, optional, expressive/emotional voices with an 'urgent' tone variant
for alerts), or Edge TTS (cloud, free, no API key and no model file to fetch
— the zero-setup fallback if neither of the above is configured).

None of the three backends is imported at module load time — only whichever
one gets selected, so installing just one of piper-tts / elevenlabs / edge-tts
is enough. This module itself deliberately has no numpy dependency
(synthesize() returns raw 16-bit PCM bytes) so it stays importable on
platforms like Termux/Android where numpy has no prebuilt wheel — the
Telegram interface needs this module just to write bytes into a WAV file, no
numeric processing involved. Callers that do need an array (e.g. the Pi voice
loop, for sounddevice playback) convert with np.frombuffer(..., dtype=np.int16)
on their own end.
"""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from pathlib import Path
from typing import Protocol

from core.config import config

logger = logging.getLogger("orion.tts")

_HEADER_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])(?:\s+|$)", re.MULTILINE)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(.+?)\*(?!\*)")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def _strip_markdown_for_speech(text: str) -> str:
    """Replies are written once and reused across every interface — plain
    text for CLI, markdown-rendering for Telegram, and spoken for voice —
    so nothing upstream avoids markdown. Left alone, a numbered list item
    like '1. Buy milk' gets treated by the sentence-splitter in
    core/agent.py as its own complete "sentence" ('1.'), which a TTS engine
    then dutifully pronounces literally; **bold**/`code` markers get read
    as literal asterisks/backticks too. Strips that formatting immediately
    before either TTS backend touches the text, without changing what
    other interfaces receive."""
    text = _HEADER_RE.sub("", text)
    text = _LIST_MARKER_RE.sub("", text)
    text = _BOLD_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub(r"\1", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    return text.strip()


class Synthesizer(Protocol):
    sample_rate: int

    def synthesize(self, text: str, urgent: bool = False) -> bytes: ...


class PiperSynthesizer:
    def __init__(self, voice_model_path: str):
        from piper.voice import PiperVoice

        self._voice = PiperVoice.load(voice_model_path)
        self.sample_rate = self._voice.config.sample_rate

    def synthesize(self, text: str, urgent: bool = False) -> bytes:
        text = _strip_markdown_for_speech(text)
        if not text:
            return b""
        # piper-tts >=1.4 replaced synthesize_stream_raw() (removed) with
        # synthesize(), which yields one AudioChunk per sentence instead of
        # raw bytes directly — audio_int16_bytes gets back to the same flat
        # 16-bit PCM format the rest of this module (and its callers) expect.
        return b"".join(chunk.audio_int16_bytes for chunk in self._voice.synthesize(text))


class ElevenLabsSynthesizer:
    """Expressive cloud TTS. The exact ElevenLabs SDK call shape has changed
    across versions; this targets the elevenlabs>=1.0 client API — adjust
    here first if upgrading the SDK breaks this."""

    sample_rate = 44100

    def __init__(self, api_key: str, voice_id: str):
        from elevenlabs.client import ElevenLabs

        self._client = ElevenLabs(api_key=api_key)
        self._voice_id = voice_id

    def synthesize(self, text: str, urgent: bool = False) -> bytes:
        text = _strip_markdown_for_speech(text)
        if not text:
            return b""
        voice_settings = (
            {"stability": 0.25, "similarity_boost": 0.8, "style": 0.6}
            if urgent
            else {"stability": 0.6, "similarity_boost": 0.75, "style": 0.2}
        )
        audio_chunks = self._client.text_to_speech.convert(
            voice_id=self._voice_id,
            text=text,
            voice_settings=voice_settings,
            output_format="pcm_44100",
        )
        return b"".join(audio_chunks)


_EDGE_TTS_NETWORK_TIMEOUT_S = 15


class EdgeTTSSynthesizer:
    """Microsoft Edge's free cloud TTS via the unofficial edge-tts package —
    no API key, no local voice model to download. The zero-setup fallback:
    useful as a working default on first install, before (or without ever)
    doing Piper's one-time voice-model download. Requires internet and the
    edge-tts package; its output is mp3, so ffmpeg (already a project
    prerequisite for faster-whisper) decodes it to the raw PCM this module's
    callers expect."""

    sample_rate = 24000  # edge-tts's own output rate

    def __init__(self, voice: str):
        import edge_tts  # noqa: F401 -- import-checked here so a missing package fails at construction, not at first synthesize() call

        self._voice = voice

    def synthesize(self, text: str, urgent: bool = False) -> bytes:
        text = _strip_markdown_for_speech(text)
        if not text:
            return b""
        try:
            mp3_bytes = asyncio.run(
                asyncio.wait_for(self._synthesize_mp3(text), timeout=_EDGE_TTS_NETWORK_TIMEOUT_S)
            )
        except (asyncio.TimeoutError, OSError) as exc:
            # _decode_mp3_to_pcm below already learned this lesson for the
            # ffmpeg subprocess step (see its own comment) -- this network
            # call needed the same fix and didn't have it. A stalled Edge
            # TTS connection (dead wifi, a DNS hiccup, Microsoft's endpoint
            # not responding) hung here indefinitely with nothing bounding
            # it, and since every caller of Synthesizer.synthesize() is
            # synchronous, that froze whichever always-on interface hit it
            # completely -- confirmed live: the Pi/laptop voice loop stopped
            # responding to the wake word at all after one stalled request,
            # because the single listening thread it needs to get back to
            # was stuck in here instead. Times out and degrades to "nothing
            # to say" instead, same as every other synthesize() failure.
            logger.warning("Edge TTS request failed or timed out (%s) -- skipping this utterance.", exc)
            return b""
        if not mp3_bytes:
            return b""
        return self._decode_mp3_to_pcm(mp3_bytes)

    async def _synthesize_mp3(self, text: str) -> bytes:
        import edge_tts

        communicate = edge_tts.Communicate(text, self._voice)
        chunks = [chunk["data"] async for chunk in communicate.stream() if chunk["type"] == "audio"]
        return b"".join(chunks)

    def _decode_mp3_to_pcm(self, mp3_bytes: bytes) -> bytes:
        # Every other subprocess.run in this codebase (telegram_bot.py's
        # ffmpeg encode, sandbox_tools.py, deploy_tool.py, ...) is bounded
        # by a timeout; this one wasn't — a truncated/corrupted mp3 stream
        # (a network hiccup partway through edge-tts's response) could hang
        # ffmpeg indefinitely, and with no caller anywhere catching that,
        # it could take down whichever always-on interface hit it (see
        # interfaces/voice/voice_loop.py's run() loop for the other half of
        # this same fix).
        result = subprocess.run(
            ["ffmpeg", "-i", "pipe:0", "-f", "s16le", "-ar", str(self.sample_rate), "-ac", "1", "pipe:1"],
            input=mp3_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=30,
        )
        return result.stdout


def get_synthesizer(piper_model_path: str | None = None) -> Synthesizer:
    if config.elevenlabs_api_key:
        return ElevenLabsSynthesizer(config.elevenlabs_api_key, config.elevenlabs_voice_id)

    if piper_model_path:
        return PiperSynthesizer(piper_model_path)

    if config.edge_tts_voice:
        try:
            return EdgeTTSSynthesizer(config.edge_tts_voice)
        except ImportError:
            pass

    raise RuntimeError(
        "No TTS backend available: set ELEVENLABS_API_KEY, download a Piper voice model "
        "(see README §7), or run `pip install edge-tts` for the free cloud fallback that "
        "needs no local model file."
    )


def find_local_piper_model() -> str | None:
    """Non-raising lookup, safe to call unconditionally — get_synthesizer()
    itself decides what to do when this comes back None (fall through to
    Edge TTS, or raise if nothing at all is configured)."""
    candidates = list(Path.home().glob(f".local/share/piper/{config.voice_language}*.onnx"))
    return str(candidates[0]) if candidates else None


def get_synthesizer_if_available() -> Synthesizer | None:
    """Like get_synthesizer, but returns None instead of raising/importing
    when no TTS backend is usable — for interfaces where voice replies are a
    nice-to-have, not a hard requirement."""
    try:
        return get_synthesizer(find_local_piper_model())
    except (ImportError, RuntimeError):
        return None
