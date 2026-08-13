from core.stt import join_confident_segments


class _Segment:
    def __init__(self, text: str, no_speech_prob: float = 0.05, compression_ratio: float = 1.0):
        self.text = text
        self.no_speech_prob = no_speech_prob
        self.compression_ratio = compression_ratio


def test_joins_confident_segments_with_low_no_speech_prob():
    segments = [_Segment("Bonjour"), _Segment(" Orion")]
    assert join_confident_segments(segments) == "Bonjour  Orion"


def test_drops_hallucinated_subtitle_credit_segments():
    """The single most common real-world failure mode: Whisper hallucinates
    plausible subtitle-credit boilerplate on near-silent/too-short audio
    instead of returning nothing — seen live as "Sous-titres réalisés par
    la communauté d'Amara.org" and "Sous-titrage ST' 501" on a real mic that
    wasn't picking up speech well."""
    segments = [_Segment("Sous-titres réalisés par la communauté d'Amara.org", no_speech_prob=0.93)]
    assert join_confident_segments(segments) == ""


def test_drops_only_the_unconfident_segments_in_a_mixed_result():
    segments = [_Segment("Quelle heure est-il"), _Segment("Sous-titrage ST' 501", no_speech_prob=0.88)]
    assert join_confident_segments(segments) == "Quelle heure est-il"


def test_empty_segment_list_returns_empty_string():
    assert join_confident_segments([]) == ""


def test_no_speech_prob_threshold_boundary_is_exclusive():
    # no_speech_prob equal to the threshold is *not* confident enough --
    # only strictly below it counts as real speech.
    at_threshold = _Segment("edge case", no_speech_prob=0.6)
    just_under = _Segment("real speech", no_speech_prob=0.599)
    assert join_confident_segments([at_threshold]) == ""
    assert join_confident_segments([just_under]) == "real speech"


def test_drops_known_hallucinations_even_with_low_no_speech_prob():
    """Regression test: "Merci d'avoir regardé." (a classic Whisper
    hallucination, alongside "Thanks for watching!") slipped through the
    no_speech_prob filter live on the user's laptop -- Whisper was
    confident about it (a low no_speech_prob), so no_speech_prob alone had
    nothing to key on. The exact-match blocklist is the second, independent
    layer that catches this class of hallucination instead."""
    segments = [_Segment("Merci d'avoir regardé.")]
    assert join_confident_segments(segments) == ""


def test_known_hallucination_match_is_case_and_punctuation_insensitive():
    segments = [_Segment("THANKS FOR WATCHING!")]
    assert join_confident_segments(segments) == ""


def test_real_speech_resembling_a_hallucination_prefix_is_not_dropped():
    # Only an exact (normalized) match is treated as a hallucination --
    # something that merely starts similarly is real speech and stays.
    text = "Merci d'avoir regardé mon dernier rapport, j'ai des questions"
    assert join_confident_segments([_Segment(text)]) == text


def test_drops_highly_repetitive_segments_via_compression_ratio():
    """The other extremely common hallucination shape alongside subtitle
    credits: degenerate word/phrase repetition ("you you you you...",
    "and and and..."), reported just as often in Whisper hallucination
    threads. Not something a phrase blocklist can cover (infinite possible
    repeated words) -- compression_ratio is Whisper's own signal for
    unusually repetitive output text, so a novel repetition hallucination
    gets caught without needing its exact words known in advance."""
    segments = [_Segment("you you you you you you you you you you", compression_ratio=3.1)]
    assert join_confident_segments(segments) == ""


def test_compression_ratio_threshold_boundary_is_exclusive():
    at_threshold = _Segment("edge case", compression_ratio=2.4)
    just_under = _Segment("real speech", compression_ratio=2.399)
    assert join_confident_segments([at_threshold]) == ""
    assert join_confident_segments([just_under]) == "real speech"


def test_normal_speech_with_ordinary_compression_ratio_is_kept():
    segments = [_Segment("Quel temps fait-il à Paris demain ?", compression_ratio=1.6)]
    assert join_confident_segments(segments) == "Quel temps fait-il à Paris demain ?"
