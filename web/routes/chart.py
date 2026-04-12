"""Chart data API route.

Returns price series, MAs, and signal markers for Chart.js.
Adds:
  - Optional ?start / ?end query params
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

from analysis.single_stock_analysis import analyze_stock
from config.credentials import FINMIND_TOKEN
from data.single_stock_loader import load_stock
from web.cache import cache

logger = logging.getLogger(__name__)
router = APIRouter()

_TWO_YEARS = 365 * 2
_MA20_WIN  = 20
_MA60_WIN  = 60


def _default_range() -> tuple[date, date]:
    end   = date.today()
    start = end - timedelta(days=_TWO_YEARS)
    return start, end


def _f(val) -> float | None:
    if val is None:
        return None
    try:
        return None if math.isnan(float(val)) else round(float(val), 2)
    except (TypeError, ValueError):
        return None


@router.get("/api/chart/{stock_id}")
async def get_chart(
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

    cache_key = ("chart", sid, str(start_date), str(end_date))
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

    # ── Build series ──────────────────────────────────────────────────────────
    daily = (
        data.daily[["date", "close"]]
        .dropna(subset=["close"])
        .sort_values("date")
        .reset_index(drop=True)
    )

    close_series = daily["close"]
    ma20 = close_series.rolling(_MA20_WIN).mean()
    ma60 = close_series.rolling(_MA60_WIN).mean()

    dates_list = [str(d) for d in daily["date"]]
    close_list = [_f(v) for v in close_series]
    ma20_list  = [_f(v) for v in ma20]
    ma60_list  = [_f(v) for v in ma60]

    price_lookup: dict[str, float] = {
        str(d): float(c) for d, c in zip(daily["date"], close_series)
    }

    # ── Signal markers ────────────────────────────────────────────────────────
    try:
        analysis = analyze_stock(data)
    except Exception as exc:
        logger.warning("analyze_stock failed for %s, signals will be empty: %s", sid, exc)
        analysis = None

    def _extract(signals, strategy_name: str) -> list[dict]:
        out = []
        for sig in (signals or []):
            if sig.direction.value != "bullish":
                continue
            date_str = str(sig.date)
            out.append({
                "date":     date_str,
                "price":    price_lookup.get(date_str),
                "score":    round(float(sig.score), 4),
                "strategy": strategy_name,
            })
        return out

    dd_signals = _extract(analysis.dd_signals if analysis else [], "davis_double")
    pv_signals = _extract(analysis.pv_signals if analysis else [], "price_volume")

    result = {
        "stock_id":   sid,
        "date_range": {"start": str(start_date), "end": str(end_date)},
        "dates":  dates_list,
        "close":  close_list,
        "ma20":   ma20_list,
        "ma60":   ma60_list,
        "signals": {
            "davis_double": dd_signals,
            "price_volume": pv_signals,
        },
    }

    cache.set(cache_key, result)
    return result
