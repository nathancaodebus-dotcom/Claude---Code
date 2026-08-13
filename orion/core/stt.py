"""Shared speech-to-text helper. Every interface that transcribes audio
(interfaces/voice/voice_loop.py, interfaces/telegram_bot.py,
interfaces/web/app.py's /api/transcribe) goes through faster-whisper the
same way and hits the same failure mode — see join_confident_segments
below — so the fix for it lives here once instead of three times.

No faster-whisper import at module level, same reasoning as core/tts.py:
this stays importable even where requirements-voice.txt isn't installed,
so callers degrade gracefully (checking for None/ImportError themselves)
instead of losing every other feature that doesn't need STT at all.
"""
from __future__ import annotations

from typing import Iterable, Protocol

# Whisper (every model size, every language — not a bug specific to this
# project) hallucinates plausible-sounding boilerplate, almost always
# subtitle-credit phrases it saw a lot of in training ("Sous-titres
# réalisés par la communauté d'Amara.org", "Sous-titrage ST' 501", "Thanks
# for watching!"), when given audio with little or no actual speech in it:
# silence, a too-short clip, background noise, a mic that isn't picking up
# the speaker well. no_speech_prob is Whisper's own per-segment confidence
# that it contains no speech at all; filtering on it catches this whole
# class of hallucination regardless of language or exact phrase, instead
# of hardcoding a blocklist of strings that would only ever cover the ones
# already seen.
NO_SPEECH_PROB_THRESHOLD = 0.6


class _Segment(Protocol):
    text: str
    no_speech_prob: float


def join_confident_segments(segments: Iterable[_Segment]) -> str:
    """faster-whisper's transcribe() returns one Segment per detected
    phrase; joins the ones Whisper itself is actually confident contain
    real speech, dropping the rest instead of feeding a caller (an LLM,
    a user) hallucinated text formatted exactly like a real transcript."""
    return " ".join(s.text for s in segments if s.no_speech_prob < NO_SPEECH_PROB_THRESHOLD).strip()
