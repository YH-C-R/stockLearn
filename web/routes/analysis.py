"""Analysis API route.

Calls existing analysis modules and serializes results to JSON.
Adds:
  - Optional ?start / ?end query params (default: 2 years back from today)
  - In-memory TTL cache (30 min) keyed by (stock_id, start, end)
  - Structured error handling with logging
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from analysis.decision_engine import make_decision
from analysis.long_term_scorer import score_long_term
from analysis.recommendation import recommend_from_decision
from analysis.short_term_scorer import score_short_term
from config.credentials import FINMIND_TOKEN
from data.single_stock_loader import load_stock
from web.cache import cache

logger = logging.getLogger(__name__)
router = APIRouter()

_TWO_YEARS = 365 * 2


def _default_range() -> tuple[date, date]:
    end   = date.today()
    start = end - timedelta(days=_TWO_YEARS)
    return start, end


def _is_nan(val) -> bool:
    try:
        return math.isnan(val)
    except (TypeError, ValueError):
        return False


@router.get("/api/analysis/{stock_id}")
async def get_analysis(
    stock_id: str,
    start: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end:   Optional[str] = Query(None, description="End date YYYY-MM-DD"),
):
    sid = stock_id.upper()

    # ── Resolve date range ────────────────────────────────────────────────────
    try:
        default_start, default_end = _default_range()
        start_date = date.fromisoformat(start) if start else default_start
        end_date   = date.fromisoformat(end)   if end   else default_end
    except ValueError as exc:
        return JSONResponse(status_code=400, content={
            "error": "Invalid date format. Use YYYY-MM-DD.",
            "detail": str(exc),
        })

    cache_key = ("analysis", sid, str(start_date), str(end_date))
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    # ── Load data ─────────────────────────────────────────────────────────────
    try:
        data = load_stock(sid, start_date, end_date, token=FINMIND_TOKEN or None)
    except Exception as exc:
        logger.exception("load_stock failed for %s", sid)
        return JSONResponse(status_code=502, content={
            "error": "Failed to fetch market data. The data provider may be unavailable.",
            "detail": str(exc),
        })

    if data.daily.empty:
        return JSONResponse(status_code=404, content={
            "error": f"No price data found for {sid} in the selected date range.",
        })

    # ── Run analysis ──────────────────────────────────────────────────────────
    try:
        lt  = score_long_term(data)
        st  = score_short_term(data)
        dec = make_decision(lt, st)
        rec = recommend_from_decision(dec)
    except Exception as exc:
        logger.exception("Analysis failed for %s", sid)
        return JSONResponse(status_code=500, content={
            "error": "Analysis computation failed.",
            "detail": str(exc),
        })

    latest = data.daily.iloc[-1]

    result = {
        "stock_id": sid,
        "date_range": {"start": str(start_date), "end": str(end_date)},
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
            "score":        round(lt.long_term_score, 4),
            "class":        lt.classification.value,
            "eps_score":    round(lt.eps_score, 4),
            "pe_score":     round(lt.pe_score, 4),
            "growth_score": round(lt.growth_score, 4),
            "current_pe":   lt.current_pe,
            "avg_pe":       lt.avg_pe,
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
            "close": float(latest["close"]) if not _is_nan(latest["close"]) else None,
            "date":  str(latest["date"]),
            "eps":   float(latest["eps"])   if not _is_nan(latest["eps"])   else None,
            "pe":    float(latest["pe"])    if not _is_nan(latest["pe"])    else None,
        },
        "warnings": data.warnings,
    }

    cache.set(cache_key, result)
    return result
