"""Backtest API route.

Calls the existing run_backtest() and summarize_backtest() and returns JSON.
Reuses:
  - data.single_stock_loader.load_stock
  - analysis.backtest.run_backtest
  - analysis.backtest_metrics.summarize_backtest
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from analysis.backtest import run_backtest
from analysis.backtest_metrics import summarize_backtest
from config.credentials import FINMIND_TOKEN
from data.single_stock_loader import load_stock

router = APIRouter()

_TWO_YEARS = 365 * 2


@router.post("/api/backtest/{stock_id}")
async def run_backtest_endpoint(stock_id: str):
    """Run a 2-year backtest for the given stock and return metrics + trades."""
    end_date   = date.today()
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

    # Actual date range present in loaded data
    actual_start = str(data.daily["date"].min())
    actual_end   = str(data.daily["date"].max())

    trades  = run_backtest(data)
    metrics = summarize_backtest(trades)

    # Serialize trades (only completed ones)
    completed = [t for t in trades if t["return"] is not None]
    trades_out = [
        {
            "entry_date":        str(t["entry_date"]),
            "exit_date":         str(t["exit_date"]),
            "entry_price":       round(t["entry_price"], 2),
            "exit_price":        round(t["exit_price"],  2),
            "return":            round(t["return"] * 100, 2),   # percent
            "decision":          t.get("decision", "—"),
            "long_term_score":   t.get("long_term_score"),
            "short_term_score":  t.get("short_term_score"),
        }
        for t in completed
    ]

    return {
        "stock_id": stock_id.upper(),
        "period": {
            "start": actual_start,
            "end":   actual_end,
        },
        "metrics": {
            "number_of_trades": metrics["number_of_trades"],
            "win_rate":         round(metrics["win_rate"] * 100, 1),        # percent
            "average_return":   round(metrics["average_return"] * 100, 2),  # percent
            "total_return":     round(metrics["total_return"] * 100, 2),    # percent
            "max_drawdown":     round(metrics["max_drawdown"] * 100, 2),    # percent
        },
        "trades": trades_out,
    }
