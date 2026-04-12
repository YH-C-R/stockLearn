from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from analysis.decision_engine import FinalDecisionResult, FinalDecision


# ---------------------------------------------------------------------------
# Recommendation tiers（UI 層）
# ---------------------------------------------------------------------------

class Recommendation(str, Enum):
    STRONG_BUY = "STRONG BUY"
    BUY        = "BUY"
    WAIT       = "WAIT"
    AVOID      = "AVOID"


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class RecommendationResult:
    stock_id:        str
    recommendation:  Recommendation
    action:          str
    confidence:      float
    summary:         str
    reasons:         list[str]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def recommend_from_decision(
    decision: FinalDecisionResult
) -> RecommendationResult:
    """
    Convert decision_engine output into user-facing recommendation.
    """

    rec = _map_decision_to_recommendation(decision.final_decision)

    summary = _build_summary(decision)

    return RecommendationResult(
        stock_id       = decision.stock_id,
        recommendation = rec,
        action         = decision.action.value,
        confidence     = decision.confidence_score,
        summary        = summary,
        reasons        = decision.reasons,
    )


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

def _map_decision_to_recommendation(decision: FinalDecision) -> Recommendation:
    if decision == FinalDecision.STRONG_BUY:
        return Recommendation.STRONG_BUY
    elif decision in (FinalDecision.BUY, FinalDecision.TRADE):
        return Recommendation.BUY
    elif decision == FinalDecision.WAIT:
        return Recommendation.WAIT
    else:
        return Recommendation.AVOID


# ---------------------------------------------------------------------------
# Summary（關鍵：人話輸出）
# ---------------------------------------------------------------------------

def _build_summary(decision: FinalDecisionResult) -> str:
    if decision.final_decision == FinalDecision.STRONG_BUY:
        return "基本面強勁 + 短期動能良好，可積極進場"

    if decision.final_decision in (FinalDecision.BUY, FinalDecision.TRADE):
        return "基本面良好，目前時機尚可，適合分批進場"

    if decision.final_decision == FinalDecision.WAIT:
        return "公司基本面不錯，但短期時機不佳，建議等待更好進場點"

    return "基本面或技術面偏弱，建議避免進場"


# ---------------------------------------------------------------------------
# Print（CLI 用）
# ---------------------------------------------------------------------------

def print_recommendation(rec: RecommendationResult) -> None:
    div = "─" * 52

    print(f"\n{div}")
    print(f"  {rec.stock_id}  —  Recommendation")
    print(div)

    print(f"  Recommendation        : {rec.recommendation.value}")
    print(f"  Action                : {rec.action}")
    print(f"  Confidence            : {rec.confidence:.4f}")

    print(f"  {'─'*48}")

    print(f"  Summary:")
    print(f"    {rec.summary}")

    print(f"  {'─'*48}")

    if rec.reasons:
        print(f"  Reasons:")
        for r in rec.reasons:
            print(f"    • {r}")

    print(f"{div}\n")