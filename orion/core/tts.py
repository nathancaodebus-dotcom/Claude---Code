"""Pluggable text-to-speech backend for the voice interface: Piper (local,
default, flat but reliable and free) or ElevenLabs (cloud, optional,
expressive/emotional voices with an 'urgent' tone variant for alerts).

Neither backend is imported at module load time — only whichever one gets
selected, so installing just one of piper-tts / elevenlabs is enough. This
module itself deliberately has no numpy dependency (synthesize() returns raw
16-bit PCM bytes) so it stays importable on platforms like Termux/Android
where numpy has no prebuilt wheel — the Telegram interface needs this module
just to write bytes into a WAV file, no numeric processing involved. Callers
that do need an array (e.g. the Pi voice loop, for sounddevice playback)
convert with np.frombuffer(..., dtype=np.int16) on their own end.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from core.config import config


class Synthesizer(Protocol):
    sample_rate: int

    def synthesize(self, text: str, urgent: bool = False) -> bytes: ...


class PiperSynthesizer:
    def __init__(self, voice_model_path: str):
        from piper.voice import PiperVoice

        self._voice = PiperVoice.load(voice_model_path)
        self.sample_rate = self._voice.config.sample_rate

    def synthesize(self, text: str, urgent: bool = False) -> bytes:
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


def get_synthesizer(piper_model_path: str | None = None) -> Synthesizer:
    if config.elevenlabs_api_key:
        return ElevenLabsSynthesizer(config.elevenlabs_api_key, config.elevenlabs_voice_id)

    if not piper_model_path:
        raise RuntimeError("No Piper voice model path given and ELEVENLABS_API_KEY is not set.")
    return PiperSynthesizer(piper_model_path)


def find_local_piper_model() -> str | None:
    """Non-raising lookup for callers that want to use TTS opportunistically
    (e.g. the Telegram bot) rather than requiring it (the Pi voice loop,
    which raises via its own _piper_model_path if none is found)."""
    candidates = list(Path.home().glob(f".local/share/piper/{config.voice_language}*.onnx"))
    return str(candidates[0]) if candidates else None


def get_synthesizer_if_available() -> Synthesizer | None:
    """Like get_synthesizer, but returns None instead of raising/importing
    when no TTS backend is usable — for interfaces where voice replies are a
    nice-to-have, not a hard requirement."""
    if config.elevenlabs_api_key:
        try:
            return get_synthesizer()
        except ImportError:
            return None  # elevenlabs package not installed

    piper_path = find_local_piper_model()
    if not piper_path:
        return None
    try:
        return get_synthesizer(piper_path)
    except ImportError:
        return None  # piper-tts package not installed
