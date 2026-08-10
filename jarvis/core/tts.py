"""Pluggable text-to-speech backend for the voice interface: Piper (local,
default, flat but reliable and free) or ElevenLabs (cloud, optional,
expressive/emotional voices with an 'urgent' tone variant for alerts).

Neither backend is imported at module load time — only whichever one gets
selected, so installing just one of piper-tts / elevenlabs is enough.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np

from core.config import config


class Synthesizer(Protocol):
    sample_rate: int

    def synthesize(self, text: str, urgent: bool = False) -> np.ndarray: ...


class PiperSynthesizer:
    def __init__(self, voice_model_path: str):
        from piper.voice import PiperVoice

        self._voice = PiperVoice.load(voice_model_path)
        self.sample_rate = self._voice.config.sample_rate

    def synthesize(self, text: str, urgent: bool = False) -> np.ndarray:
        chunks = list(self._voice.synthesize_stream_raw(text))
        return np.concatenate([np.frombuffer(c, dtype=np.int16) for c in chunks])


class ElevenLabsSynthesizer:
    """Expressive cloud TTS. The exact ElevenLabs SDK call shape has changed
    across versions; this targets the elevenlabs>=1.0 client API — adjust
    here first if upgrading the SDK breaks this."""

    sample_rate = 44100

    def __init__(self, api_key: str, voice_id: str):
        from elevenlabs.client import ElevenLabs

        self._client = ElevenLabs(api_key=api_key)
        self._voice_id = voice_id

    def synthesize(self, text: str, urgent: bool = False) -> np.ndarray:
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
        raw = b"".join(audio_chunks)
        return np.frombuffer(raw, dtype=np.int16)


def get_synthesizer(piper_model_path: str | None = None) -> Synthesizer:
    if config.elevenlabs_api_key:
        return ElevenLabsSynthesizer(config.elevenlabs_api_key, config.elevenlabs_voice_id)

    if not piper_model_path:
        raise RuntimeError("No Piper voice model path given and ELEVENLABS_API_KEY is not set.")
    return PiperSynthesizer(piper_model_path)
