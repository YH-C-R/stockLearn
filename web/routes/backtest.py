"""Backtest API route.

Adds:
  - Optional ?start / ?end query params
  - Structured error handling with logging
  - (Backtest is not cached — it is user-triggered on demand)
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from analysis.backtest import run_backtest
from analysis.backtest_metrics import summarize_backtest
from config.credentials import FINMIND_TOKEN
from data.single_stock_loader import load_stock

logger = logging.getLogger(__name__)
router = APIRouter()

_TWO_YEARS = 365 * 2


def _default_range() -> tuple[date, date]:
    end   = date.today()
    start = end - timedelta(days=_TWO_YEARS)
    return start, end


@router.post("/api/backtest/{stock_id}")
async def run_backtest_endpoint(
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

    actual_start = str(data.daily["date"].min())
    actual_end   = str(data.daily["date"].max())

    # ── Run backtest ──────────────────────────────────────────────────────────
    try:
        trades  = run_backtest(data)
        metrics = summarize_backtest(trades)
    except Exception as exc:
        logger.exception("Backtest failed for %s", sid)
        return JSONResponse(status_code=500, content={
            "error": "Backtest computation failed.",
            "detail": str(exc),
        })

    completed  = [t for t in trades if t["return"] is not None]
    trades_out = [
        {
            "entry_date":       str(t["entry_date"]),
            "exit_date":        str(t["exit_date"]),
            "entry_price":      round(t["entry_price"], 2),
            "exit_price":       round(t["exit_price"],  2),
            "return":           round(t["return"] * 100, 2),
            "decision":         t.get("decision", "—"),
            "long_term_score":  t.get("long_term_score"),
            "short_term_score": t.get("short_term_score"),
        }
        for t in completed
    ]

    return {
        "stock_id": sid,
        "period": {"start": actual_start, "end": actual_end},
        "metrics": {
            "number_of_trades": metrics["number_of_trades"],
            "win_rate":         round(metrics["win_rate"] * 100, 1),
            "average_return":   round(metrics["average_return"] * 100, 2),
            "total_return":     round(metrics["total_return"] * 100, 2),
            "max_drawdown":     round(metrics["max_drawdown"] * 100, 2),
        },
        "trades": trades_out,
    }
