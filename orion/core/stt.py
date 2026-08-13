"""Shared speech-to-text helper. Every interface that transcribes audio
(interfaces/voice/voice_loop.py, interfaces/telegram_bot.py,
interfaces/web/app.py's /api/transcribe) goes through faster-whisper the
same way and hits the same failure mode — see join_confident_segments
below — so the fix for it lives here once instead of three times.

No faster-whisper import at module level, same reasoning as core/tts.py:
this stays importable even where requirements-voice.txt isn't installed,
so callers degrade gracefully (checking for None/ImportError themselves)
instead of losing every other feature that doesn't need STT at all.

Whisper hallucinating boilerplate on audio with little or no real speech
in it — silence, a too-short clip, background noise, a mic that isn't
picking up the speaker well — is not a bug specific to this project or
this deployment; it's one of the most widely reported failure modes of
every Whisper variant (openai/whisper, faster-whisper, whisper.cpp) across
every language, tracked in dozens of upstream GitHub issues/discussions
(openai/whisper#679, #928, #1873, #1606; ggml-org/whisper.cpp#2660; among
others). Three independent, complementary layers below, because no single
one catches everything on its own — confirmed live during this project's
own testing, where a hallucination Whisper was confident about ("Merci
d'avoir regardé.") sailed straight through the no_speech_prob check that
caught an earlier one:

1. no_speech_prob — Whisper's own per-segment confidence that a segment
   contains no speech at all. Catches most hallucinations, but not the
   ones Whisper is (wrongly) confident about.
2. A curated blocklist of the exact phrases Whisper is most famous for
   hallucinating — overwhelmingly subtitle/broadcast credits and video
   outros it saw enormously often in training (YouTube auto-captions,
   Amara.org community subtitles, German ZDF/WDR credits, Chinese/Russian
   fansub credits...). Catches confidently-hallucinated boilerplate
   no_speech_prob misses, but only phrases already known and reported.
3. compression_ratio — Whisper's own per-segment gzip compression ratio
   of the output text. A segment that's mostly repeated words/phrases
   ("you you you you...", "and and and...") compresses unusually well;
   a high ratio is Whisper's own signal for exactly that kind of
   degenerate repetition, which is the other extremely common
   hallucination shape reported alongside the subtitle-credit one.
   Generalizes past the specific phrases in the blocklist to catch that
   whole failure shape regardless of the words involved. 2.4 is the same
   default openai/whisper itself uses internally for this check.
"""
from __future__ import annotations

from typing import Iterable, Protocol

NO_SPEECH_PROB_THRESHOLD = 0.6
COMPRESSION_RATIO_THRESHOLD = 2.4

# Sources: openai/whisper discussions #679, #928, #1873, #1606;
# ggml-org/whisper.cpp#2660 — community-reported hallucinations, deduped
# and normalized (lowercase, no trailing punctuation — see
# _is_known_hallucination). Deliberately only exact, unambiguous
# subtitle-credit/outro phrases a real user essentially never says
# verbatim as a complete utterance — not generic short words/phrases that
# a real (if terse) request could plausibly match.
_KNOWN_HALLUCINATIONS = frozenset(
    {
        # French
        "sous-titres réalisés par la communauté d'amara.org",
        "sous-titrage st' 501",
        "sous-titrage société radio-canada",
        "merci d'avoir regardé cette vidéo",
        "merci d'avoir regardé",
        "n'hésitez pas à vous abonner",
        "abonnez-vous à la chaîne",
        "abonnez-vous",
        "à bientôt pour une nouvelle vidéo",
        # English
        "thanks for watching",
        "thank you for watching",
        "thank you for watching! applause",
        "thanks for watching! applause",
        "please subscribe",
        "subscribe to my channel",
        "don't forget to subscribe",
        "transcription by castingwords",
        "the end",
        # German
        "untertitel im auftrag des zdf",
        "untertitel der amara.org-community",
        "copyright wdr 2021",
        # Chinese
        "由 amara.org 社群提供的字幕",
        "中文字幕志愿者 杨茜茜",
        "字幕志愿者 杨茜茜",
        # Russian
        "субтитры сделал dimatorzok",
    }
)


class _Segment(Protocol):
    text: str
    no_speech_prob: float
    compression_ratio: float


def _is_known_hallucination(text: str) -> bool:
    return text.strip().strip(".!?").lower() in _KNOWN_HALLUCINATIONS


def join_confident_segments(segments: Iterable[_Segment]) -> str:
    """faster-whisper's transcribe() returns one Segment per detected
    phrase; joins the ones that pass all three hallucination checks
    above, dropping the rest instead of feeding a caller (an LLM, a user)
    hallucinated text formatted exactly like a real transcript."""
    kept = [
        s.text
        for s in segments
        if s.no_speech_prob < NO_SPEECH_PROB_THRESHOLD
        and s.compression_ratio < COMPRESSION_RATIO_THRESHOLD
        and not _is_known_hallucination(s.text)
    ]
    return " ".join(kept).strip()
