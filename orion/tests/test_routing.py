"""core/routing.py picks Claude Haiku or Sonnet per user message by a
bilingual heuristic complexity score, ported from OpenJarvis's real
complexity/router modules (see core/routing.py's docstring). These tests
cover both languages' signal patterns and the threshold/escalation rules
that turn a score into a model choice."""
from __future__ import annotations

from core.routing import score_complexity, select_model

STRONG = "claude-sonnet-5"
FAST = "claude-haiku-4-5-20251001"


def test_trivial_short_query_scores_low():
    result = score_complexity("Hi")
    assert result.score <= 0.20
    assert result.tier == "trivial"


def test_short_french_greeting_scores_low():
    result = score_complexity("Salut, ça va ?")
    assert result.score <= 0.20


def test_english_code_signal_detected():
    result = score_complexity("Can you fix this: `def foo(): return x/0`")
    assert result.signals["has_code"] is True


def test_french_code_signal_detected():
    result = score_complexity("Peux-tu déboguer cette fonction pour moi ?")
    assert result.signals["has_code"] is True


def test_english_math_signal_detected():
    result = score_complexity("Solve this equation for x and show the derivative.")
    assert result.signals["has_math"] is True


def test_french_math_signal_detected():
    result = score_complexity("Peux-tu résoudre cette équation et calculer la dérivée ?")
    assert result.signals["has_math"] is True


def test_english_reasoning_signal_detected():
    result = score_complexity("Explain why this approach works, step by step.")
    assert result.signals["has_reasoning"] is True


def test_french_reasoning_signal_detected():
    result = score_complexity("Explique-moi pourquoi cette approche fonctionne, étape par étape.")
    assert result.signals["has_reasoning"] is True


def test_long_multi_part_query_scores_high():
    query = (
        "First, analyze the current architecture. Then, compare it against the "
        "alternative we discussed, weighing the pros and cons of each. Additionally, "
        "explain step by step why the tradeoffs favor one over the other, and finally "
        "draft a short report summarizing your reasoning for the whole team to review. "
        "1. What breaks first? 2. What's the migration cost? 3. What's the timeline?"
    )
    result = score_complexity(query)
    assert result.score >= 0.55
    assert result.tier in ("complex", "very_complex")


def test_score_is_clamped_between_zero_and_one():
    query = (
        "```code``` " * 5
        + "solve equation derivative matrix "
        + "explain analyze compare why step by step "
        + "then also then also additionally furthermore "
        + "write an essay create design draft "
        + "? ? ? ? ?"
    )
    result = score_complexity(query)
    assert 0.0 <= result.score <= 1.0


def test_select_model_routes_trivial_query_to_fast_model():
    model, result = select_model("Hi", strong_model=STRONG, fast_model=FAST)
    assert model == FAST
    assert result.score <= 0.20


def test_select_model_routes_code_query_to_strong_model_even_if_short():
    model, _ = select_model("fix `x=1/0`", strong_model=STRONG, fast_model=FAST)
    assert model == STRONG


def test_select_model_routes_math_query_to_strong_model_even_if_short():
    model, _ = select_model("calculate the integral of x^2", strong_model=STRONG, fast_model=FAST)
    assert model == STRONG


def test_select_model_routes_high_complexity_query_to_strong_model():
    query = (
        "Explain step by step why this architecture is slower, then compare it "
        "against three alternatives and give me the tradeoffs for each. 1. cost? "
        "2. latency? 3. maintainability? Also draft a short report on your findings."
    )
    model, result = select_model(query, strong_model=STRONG, fast_model=FAST)
    assert model == STRONG
    assert result.score >= 0.55


def test_select_model_routes_ambiguous_middle_ground_to_strong_model():
    """A longer, mildly multi-part query with no code/math/reasoning signal
    lands in the ambiguous middle between the two thresholds -- the router
    favors the model whose failure mode is 'a bit slower', not 'confidently
    wrong'."""
    query = (
        "Tell me something interesting about the history of the Eiffel Tower. "
        "I've always wondered about the era it was built in and the people involved. "
        "What was Paris like back then? Did most residents actually like the tower "
        "when it was first unveiled to visitors from around the world, or did many "
        "of them dislike it at first? I would love a few little-known details about "
        "the people behind it, plus any fun trivia about its early years as a "
        "landmark that most tourists never hear about today."
    )
    result = score_complexity(query)
    assert 0.20 < result.score < 0.55
    model, _ = select_model(query, strong_model=STRONG, fast_model=FAST)
    assert model == STRONG
