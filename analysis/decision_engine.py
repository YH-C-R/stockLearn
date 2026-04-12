"""Decision engine: combine long-term and short-term scores into a final decision.

Long-term quality dominates the decision; short-term timing only affects
whether to act now or wait for a better entry.

Decision matrix
---------------
  Long-term       Short-term    Decision
  ──────────────  ────────────  ──────────────
  STRONG_LONG   + GOOD_ENTRY  → STRONG_BUY
  STRONG_LONG   + WAIT        → WAIT
  STRONG_LONG   + AVOID       → AVOID
  NEUTRAL       + GOOD_ENTRY  → TRADE
  NEUTRAL       + WAIT        → WAIT
  NEUTRAL       + AVOID       → AVOID
  WEAK          + (any)       → AVOID

Action mapping
--------------
  STRONG_BUY → BUY
  BUY        → BUY
  TRADE      → BUY
  WAIT       → WAIT
  AVOID      → AVOID

Usage
-----
    from analysis.long_term_scorer import score_long_term
    from analysis.short_term_scorer import score_short_term
    from analysis.decision_engine import make_decision, print_decision

    lt  = score_long_term(data)
    st  = score_short_term(data)
    dec = make_decision(lt, st)
    print_decision(dec)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from analysis.long_term_scorer import LongTermClass, LongTermScoreResult
from analysis.short_term_scorer import ShortTermScoreResult, TimingSignal


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FinalDecision(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY        = "BUY"
    TRADE      = "TRADE"
    WAIT       = "WAIT"
    AVOID      = "AVOID"


class Action(str, Enum):
    BUY  = "BUY"
    WAIT = "WAIT"
    AVOID = "AVOID"


# ---------------------------------------------------------------------------
# Action mapping (single source of truth)
# ---------------------------------------------------------------------------

_ACTION: dict[FinalDecision, Action] = {
    FinalDecision.STRONG_BUY: Action.BUY,
    FinalDecision.BUY:        Action.BUY,
    FinalDecision.TRADE:      Action.BUY,
    FinalDecision.WAIT:       Action.WAIT,
    FinalDecision.AVOID:      Action.AVOID,
}

# Decision matrix: (LongTermClass, TimingSignal) → FinalDecision
_DECISION_MATRIX: dict[tuple[LongTermClass, TimingSignal], FinalDecision] = {
    (LongTermClass.STRONG_LONG, TimingSignal.GOOD_ENTRY): FinalDecision.STRONG_BUY,
    (LongTermClass.STRONG_LONG, TimingSignal.WAIT):       FinalDecision.WAIT,
    (LongTermClass.STRONG_LONG, TimingSignal.AVOID):      FinalDecision.AVOID,
    (LongTermClass.NEUTRAL,     TimingSignal.GOOD_ENTRY): FinalDecision.TRADE,
    (LongTermClass.NEUTRAL,     TimingSignal.WAIT):       FinalDecision.WAIT,
    (LongTermClass.NEUTRAL,     TimingSignal.AVOID):      FinalDecision.AVOID,
    (LongTermClass.WEAK,        TimingSignal.GOOD_ENTRY): FinalDecision.AVOID,
    (LongTermClass.WEAK,        TimingSignal.WAIT):       FinalDecision.AVOID,
    (LongTermClass.WEAK,        TimingSignal.AVOID):      FinalDecision.AVOID,
}


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class FinalDecisionResult:
    """Combined output of the decision engine.

    Attributes
    ----------
    stock_id         : Stock ticker.
    final_decision   : STRONG_BUY / BUY / TRADE / WAIT / AVOID.
    action           : Simplified action: BUY / WAIT / AVOID.
    confidence_score : 0.7 × long_term_score + 0.3 × short_term_score.
    reasons          : Combined key reasons from both scorers (long-term first).
    long_term_class  : Classification from the long-term scorer.
    timing_signal    : Signal from the short-term scorer.
    long_term_score  : Raw long-term composite score.
    short_term_score : Raw short-term composite score.
    """
    stock_id:         str
    final_decision:   FinalDecision
    action:           Action
    confidence_score: float
    reasons:          list[str]
    long_term_class:  LongTermClass
    timing_signal:    TimingSignal
    long_term_score:  float
    short_term_score: float


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def make_decision(
    long_term:  LongTermScoreResult,
    short_term: ShortTermScoreResult,
) -> FinalDecisionResult:
    """Combine long-term and short-term scores into a final trading decision.

    Parameters
    ----------
    long_term  : Output of ``score_long_term()``.
    short_term : Output of ``score_short_term()``.

    Returns
    -------
    FinalDecisionResult.
    """
    decision = _DECISION_MATRIX[
        (long_term.classification, short_term.timing_signal)
    ]
    action           = _ACTION[decision]
    confidence_score = round(
        0.7 * long_term.long_term_score + 0.3 * short_term.short_term_score, 4
    )
    reasons = _merge_reasons(long_term.key_reasons, short_term.key_reasons)

    return FinalDecisionResult(
        stock_id         = long_term.stock_id,
        final_decision   = decision,
        action           = action,
        confidence_score = confidence_score,
        reasons          = reasons,
        long_term_class  = long_term.classification,
        timing_signal    = short_term.timing_signal,
        long_term_score  = long_term.long_term_score,
        short_term_score = short_term.short_term_score,
    )


def print_decision(result: FinalDecisionResult) -> None:
    """Print a formatted decision report to stdout."""
    div = "─" * 52

    def row(label: str, value: object) -> None:
        print(f"  {label:<24}: {value}")

    def frow(label: str, value: float, fmt: str = ".4f") -> None:
        print(f"  {label:<24}: {value:{fmt}}")

    print(f"\n{div}")
    print(f"  {result.stock_id}  —  Final Decision")
    print(div)

    row("Decision",         result.final_decision.value)
    row("Action",           result.action.value)
    frow("Confidence score", result.confidence_score)

    print(f"  {'─'*48}")

    row("Long-term class",  result.long_term_class.value)
    row("Timing signal",    result.timing_signal.value)
    frow("Long-term score",  result.long_term_score)
    frow("Short-term score", result.short_term_score)

    print(f"  {'─'*48}")

    if result.reasons:
        print(f"  {'Reasons':<24}:")
        for r in result.reasons:
            print(f"    • {r}")

    print(f"{div}\n")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _merge_reasons(
    long_reasons:  list[str],
    short_reasons: list[str],
) -> list[str]:
    """Interleave long-term and short-term reasons, long-term first."""
    merged: list[str] = []
    for reason in long_reasons:
        merged.append(f"[LT] {reason}")
    for reason in short_reasons:
        merged.append(f"[ST] {reason}")
    return merged
