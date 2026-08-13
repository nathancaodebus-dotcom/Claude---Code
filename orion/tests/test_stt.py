from core.stt import join_confident_segments


class _Segment:
    def __init__(self, text: str, no_speech_prob: float):
        self.text = text
        self.no_speech_prob = no_speech_prob


def test_joins_confident_segments_with_low_no_speech_prob():
    segments = [_Segment("Bonjour", 0.05), _Segment(" Orion", 0.1)]
    assert join_confident_segments(segments) == "Bonjour  Orion"


def test_drops_hallucinated_subtitle_credit_segments():
    """The single most common real-world failure mode: Whisper hallucinates
    plausible subtitle-credit boilerplate on near-silent/too-short audio
    instead of returning nothing — seen live as "Sous-titres réalisés par
    la communauté d'Amara.org" and "Sous-titrage ST' 501" on a real mic that
    wasn't picking up speech well."""
    segments = [_Segment("Sous-titres réalisés par la communauté d'Amara.org", 0.93)]
    assert join_confident_segments(segments) == ""


def test_drops_only_the_unconfident_segments_in_a_mixed_result():
    segments = [_Segment("Quelle heure est-il", 0.05), _Segment("Sous-titrage ST' 501", 0.88)]
    assert join_confident_segments(segments) == "Quelle heure est-il"


def test_empty_segment_list_returns_empty_string():
    assert join_confident_segments([]) == ""


def test_threshold_boundary_is_exclusive():
    # no_speech_prob equal to the threshold is *not* confident enough --
    # only strictly below it counts as real speech.
    at_threshold = _Segment("edge case", 0.6)
    just_under = _Segment("real speech", 0.599)
    assert join_confident_segments([at_threshold]) == ""
    assert join_confident_segments([just_under]) == "real speech"
