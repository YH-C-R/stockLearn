"""Chart data API route.

Returns price series, MAs, and signal markers for Chart.js.
Reuses:
  - data.single_stock_loader.load_stock
  - analysis.single_stock_analysis.analyze_stock
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from analysis.single_stock_analysis import analyze_stock
from config.credentials import FINMIND_TOKEN
from data.single_stock_loader import load_stock

router = APIRouter()

_TWO_YEARS  = 365 * 2
_MA20_WIN   = 20
_MA60_WIN   = 60


@router.get("/api/chart/{stock_id}")
async def get_chart(stock_id: str):
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
            content={"error": f"No data for {stock_id}"},
        )

    daily = (
        data.daily[["date", "close"]]
        .dropna(subset=["close"])
        .sort_values("date")
        .reset_index(drop=True)
    )

    close_series = daily["close"]

    # ── Moving averages ───────────────────────────────────────────────────────
    ma20 = close_series.rolling(_MA20_WIN).mean()
    ma60 = close_series.rolling(_MA60_WIN).mean()

    def _f(val) -> float | None:
        return None if (val is None or (isinstance(val, float) and math.isnan(val))) else round(float(val), 2)

    dates_list = [str(d) for d in daily["date"]]
    close_list = [_f(v) for v in close_series]
    ma20_list  = [_f(v) for v in ma20]
    ma60_list  = [_f(v) for v in ma60]

    # ── Signal markers via analyze_stock ─────────────────────────────────────
    # Build a date → close lookup for annotating signal prices
    price_lookup: dict[str, float] = {
        str(d): float(c)
        for d, c in zip(daily["date"], close_series)
    }

    analysis = analyze_stock(data)

    def _extract(signals, strategy_name: str) -> list[dict]:
        """Keep only bullish signals; attach the close price on that date."""
        out = []
        for sig in signals:
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

    dd_signals = _extract(analysis.dd_signals, "davis_double")
    pv_signals = _extract(analysis.pv_signals, "price_volume")

    return {
        "stock_id": stock_id.upper(),
        "dates":    dates_list,
        "close":    close_list,
        "ma20":     ma20_list,
        "ma60":     ma60_list,
        "signals": {
            "davis_double": dd_signals,
            "price_volume": pv_signals,
        },
    }
