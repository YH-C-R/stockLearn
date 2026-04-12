"""Analysis API routes.

Calls existing analysis modules and serializes results to JSON.
All imports are from the existing codebase — nothing is reimplemented here.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from analysis.decision_engine import make_decision
from analysis.long_term_scorer import score_long_term
from analysis.recommendation import recommend_from_decision
from analysis.short_term_scorer import score_short_term
from config.credentials import FINMIND_TOKEN
from data.single_stock_loader import load_stock

router = APIRouter()

_TWO_YEARS = 365 * 2


def _today() -> date:
    return date.today()


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/api/analysis/{stock_id}")
async def get_analysis(stock_id: str):
    """Run full analysis for a stock and return scores + recommendation as JSON."""
    end_date   = _today()
    start_date = end_date - timedelta(days=_TWO_YEARS)

    data = load_stock(
        stock_id.upper(),
        start_date,
        end_date,
        token=FINMIND_TOKEN or None,
    )

    if data.daily.empty:
        return JSONResponse(
            status_code=404,
            content={"error": f"No data available for {stock_id}"},
        )

    lt  = score_long_term(data)
    st  = score_short_term(data)
    dec = make_decision(lt, st)
    rec = recommend_from_decision(dec)

    # Latest values for the detail panel
    latest = data.daily.iloc[-1] if not data.daily.empty else None

    return {
        "stock_id": stock_id.upper(),
        "recommendation": {
            "label":      rec.recommendation.value,
            "action":     rec.action,
            "confidence": round(rec.confidence, 4),
            "summary":    rec.summary,
            "reasons":    rec.reasons,
        },
        "decision": {
            "final":           dec.final_decision.value,
            "long_term_class": dec.long_term_class.value,
            "timing_signal":   dec.timing_signal.value,
        },
        "long_term": {
            "score":       round(lt.long_term_score, 4),
            "class":       lt.classification.value,
            "eps_score":   round(lt.eps_score, 4),
            "pe_score":    round(lt.pe_score, 4),
            "growth_score":round(lt.growth_score, 4),
            "current_pe":  lt.current_pe,
            "avg_pe":      lt.avg_pe,
            "eps_quarters": lt.eps_quarters[-4:] if lt.eps_quarters else [],
        },
        "short_term": {
            "score":        round(st.short_term_score, 4),
            "signal":       st.timing_signal.value,
            "price_score":  round(st.price_score, 4),
            "volume_score": round(st.volume_score, 4),
            "margin_score": round(st.margin_score, 4),
            "ma20":         round(st.ma20, 2) if st.ma20 else None,
            "ma60":         round(st.ma60, 2) if st.ma60 else None,
        },
        "latest": {
            "close": float(latest["close"]) if latest is not None else None,
            "date":  str(latest["date"])    if latest is not None else None,
            "eps":   float(latest["eps"])   if latest is not None and not _is_nan(latest["eps"]) else None,
            "pe":    float(latest["pe"])    if latest is not None and not _is_nan(latest["pe"])  else None,
        },
        "warnings": data.warnings,
    }


def _is_nan(val) -> bool:
    try:
        import math
        return math.isnan(val)
    except (TypeError, ValueError):
        return False
