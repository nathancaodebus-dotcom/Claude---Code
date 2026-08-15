"""Cloud model routing: picks Claude Haiku or Sonnet per user message instead
of always paying Sonnet's latency/cost for questions that don't need it.

Design lifted from — and credited to — OpenJarvis's query-complexity router
(github.com/open-jarvis/OpenJarvis, src/openjarvis/learning/routing/), a
Stanford Hazy Research project this session reviewed directly against
Orion: a weighted multi-signal heuristic score (length, code/math domain
signals, reasoning/multi-step phrasing, sub-task count, creative-writing
signals) mapped to a complexity tier. Adapted for Orion specifically:

- OpenJarvis routes across an open-ended registry of differently-sized
  *local* models; Orion only ever has two cloud tiers (config.fast_model /
  config.model), so the router here is a binary threshold instead of a
  general model-registry search.
- Every regex is bilingual (French + English) — OpenJarvis's patterns are
  English-only, but Orion's actual user writes in French.
- No local-model or urgency-override rules (nothing to route across, no
  urgency signal in this codebase) — only the parts that transfer.

Router logic:
1. Code or math signals -> Sonnet (both benefit from stronger reasoning,
   and misrouting either to Haiku risks a subtly wrong answer that's easy
   to miss, unlike a merely slower one).
2. Below a low-complexity threshold with neither of the above -> Haiku.
3. High complexity, multi-step phrasing, or explicit reasoning language
   -> Sonnet.
4. Everything in between defaults to Sonnet -- ambiguous cases favor the
   model whose failure mode is "a bit slower," not "confidently wrong."
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# --- Signal patterns (French + English) -----------------------------------

_CODE_PATTERNS = re.compile(
    r"```|`[^`]+`|\bdef\s|\bclass\s|\bimport\s|\bfunction\s|\bconst\s|\bvar\s|\blet\s|"
    r"\bif\s*\(|->|=>|\{\s*\}|\bfor\s+\w+\s+in\s|#include|System\.out|"
    r"\bcode\b|\bfonction\b|\bclasse\b|\bd[ée]bug(?:ue|ger)?\b",
    re.IGNORECASE,
)
_MATH_PATTERNS = re.compile(
    r"\bsolve\b|\bintegral\b|\bequation\b|\bproof\b|\bderivative\b|\bmatrix\b|"
    r"\btheorem\b|\bcalculate\b|\bcompute\b|\bsigma\b|\bsum\b|\blimit\b|\bprobability\b|"
    r"\br[ée]sou(?:s|dre)\b|\b[ée]quation\b|\bd[ée]monstration\b|\bd[ée]riv[ée]e\b|"
    r"\bmatrice\b|\bth[ée]or[èe]me\b|\bcalcul(?:e|er)?\b|\bprobabilit[ée]\b",
    re.IGNORECASE,
)
_REASONING_PATTERNS = re.compile(
    r"\bexplain\b|\banalyze\b|\bcompare\b|\bwhy\b"
    r"|\bstep[- ]by[- ]step\b|\breason\b|\bthink\b"
    r"|\bpros\s+and\s+cons\b|\btrade-?\s*offs?\b|\bevaluate\b"
    r"|\bexplique(?:r)?\b|\banalys(?:e|er)\b|\bcompar(?:e|er)\b|\bpourquoi\b"
    r"|\b[ée]tape\s+par\s+[ée]tape\b|\br[ée]fl[ée]chi(?:s|r)\b"
    r"|\bavantages?\s+et\s+inconv[ée]nients?\b|\b[ée]valu(?:e|er)\b|\bcompromis\b",
    re.IGNORECASE,
)
_MULTI_STEP_PATTERNS = re.compile(
    r"\bthen\b.*\bthen\b|\bfirst\b.*\bnext\b|\bstep\s*\d"
    r"|\b(?:and\s+also|additionally|furthermore)\b|\b\d+\.\s"
    r"|\bpuis\b.*\bpuis\b|\bd[’']abord\b.*\bensuite\b|\bensuite\b.*\bensuite\b"
    r"|\b(?:et\s+aussi|de\s+plus|par\s+ailleurs)\b",
    re.IGNORECASE | re.DOTALL,
)
_CREATIVE_PATTERNS = re.compile(
    r"\bwrite\b.*\b(?:essay|story|article|report|poem)\b"
    r"|\bgenerate\b.*\b(?:code|script|program)\b"
    r"|\bcreate\b|\bdesign\b|\bdraft\b|\bcompose\b"
    r"|\b[ée]cri(?:s|re)\b.*\b(?:essai|histoire|article|rapport|po[èe]me)\b"
    r"|\bg[ée]n[èe]re\b.*\b(?:code|script|programme)\b"
    r"|\bcr[ée]e(?:r)?\b|\bcon[çc]oi(?:s|vre)\b|\br[ée]dige(?:r)?\b",
    re.IGNORECASE,
)

_TOKEN_TIERS = {
    "trivial": 0.15,
    "simple": 0.30,
    "moderate": 0.55,
    "complex": 0.80,
}
# Below this, and with no code/math signal, a message routes to the fast
# model; the score alone (not the tier name) is what the router acts on.
_LOW_COMPLEXITY_THRESHOLD = 0.20
_HIGH_COMPLEXITY_THRESHOLD = 0.55


@dataclass(frozen=True)
class ComplexityResult:
    score: float  # 0.0-1.0
    tier: str
    signals: dict


def score_complexity(query: str) -> ComplexityResult:
    """Scores a query's complexity from 0.0 (trivial) to 1.0 (very complex)
    as a weighted combination of independent signals — see module
    docstring for where this design comes from."""
    signals: dict = {}
    score = 0.0

    length = len(query)
    if length < 20:
        length_score = 0.0
    elif length < 100:
        length_score = 0.3
    elif length < 300:
        length_score = 0.6
    elif length < 800:
        length_score = 0.8
    else:
        length_score = 1.0
    signals["length"] = length_score
    score += 0.20 * length_score

    has_code = bool(_CODE_PATTERNS.search(query))
    has_math = bool(_MATH_PATTERNS.search(query))
    domain_score = 0.0
    if has_code:
        domain_score = max(domain_score, 0.7)
    if has_math:
        domain_score = max(domain_score, 0.8)
    if has_code and has_math:
        domain_score = 1.0
    signals["domain"] = domain_score
    signals["has_code"] = has_code
    signals["has_math"] = has_math
    score += 0.25 * domain_score

    has_reasoning = bool(_REASONING_PATTERNS.search(query))
    has_multi_step = bool(_MULTI_STEP_PATTERNS.search(query))
    reasoning_score = 0.0
    if has_reasoning:
        reasoning_score = 0.6
    if has_multi_step:
        reasoning_score = max(reasoning_score, 0.8)
    if has_reasoning and has_multi_step:
        reasoning_score = 1.0
    signals["reasoning"] = reasoning_score
    signals["has_reasoning"] = has_reasoning
    signals["has_multi_step"] = has_multi_step
    score += 0.25 * reasoning_score

    n_questions = query.count("?")
    n_subtasks = len(re.findall(r"^\s*\d+[.)]\s", query, re.MULTILINE)) + len(
        re.findall(r"^\s*[-*]\s", query, re.MULTILINE)
    )
    multi_part = n_questions + n_subtasks
    if multi_part <= 1:
        multi_score = 0.0
    elif multi_part <= 3:
        multi_score = 0.5
    else:
        multi_score = 1.0
    signals["multi_part"] = multi_score
    score += 0.15 * multi_score

    has_creative = bool(_CREATIVE_PATTERNS.search(query))
    creative_score = 0.7 if has_creative else 0.0
    signals["creative"] = creative_score
    signals["has_creative"] = has_creative
    score += 0.15 * creative_score

    score = max(0.0, min(1.0, score))

    if score < _TOKEN_TIERS["trivial"]:
        tier = "trivial"
    elif score < _TOKEN_TIERS["simple"]:
        tier = "simple"
    elif score < _TOKEN_TIERS["moderate"]:
        tier = "moderate"
    elif score < _TOKEN_TIERS["complex"]:
        tier = "complex"
    else:
        tier = "very_complex"

    return ComplexityResult(score=round(score, 3), tier=tier, signals=signals)


def select_model(query: str, *, strong_model: str, fast_model: str) -> tuple[str, ComplexityResult]:
    """Picks strong_model (Sonnet) or fast_model (Haiku) for a user message.
    Returns the chosen model alongside the ComplexityResult that drove the
    decision, so callers can log/expose the reasoning rather than routing
    as an opaque black box."""
    result = score_complexity(query)

    # Code/math get the strong model unconditionally, ahead of the
    # low-complexity check below -- a short "fix this: `x=1/0`" is exactly
    # the kind of message the length signal alone would call trivial.
    if result.signals["has_code"] or result.signals["has_math"]:
        return strong_model, result

    if result.score <= _LOW_COMPLEXITY_THRESHOLD:
        return fast_model, result

    if result.score >= _HIGH_COMPLEXITY_THRESHOLD or result.signals["has_reasoning"]:
        return strong_model, result

    # Ambiguous middle ground: favor the model whose failure mode is
    # "answered a bit slower than necessary" over "confidently wrong."
    return strong_model, result
