"""Shared backtest flow used by both the CLI script and the web API.

Centralises:
  - warmup-period calculation
  - data loading via load_stock
  - run_backtest with analysis_start_date
  - summarize_backtest
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from analysis.backtest import run_backtest
from analysis.backtest_metrics import summarize_backtest
from data.single_stock_loader import load_stock

WARMUP_DAYS = 400


@dataclass
class BacktestResult:
    trades: list[dict]
    metrics: dict
    requested_start: date
    requested_end: date
    loaded_start: date   # earliest date actually present in loaded data
    loaded_end: date     # latest  date actually present in loaded data


class NoDataError(ValueError):
    """Raised when load_stock returns no price rows."""


def run_backtest_flow(
    stock_id: str,
    start_date: date,
    end_date: date,
    token: str | None = None,
    warmup_days: int = WARMUP_DAYS,
) -> BacktestResult:
    """Load data with a warmup window, run the backtest, and return results.

    Parameters
    ----------
    stock_id:    Ticker symbol (e.g. "2330").
    start_date:  First date of the analysis period (trades may not begin before this).
    end_date:    Last date of the analysis period.
    token:       FinMind API token; None falls back to unauthenticated access.
    warmup_days: Calendar days to prepend before start_date for indicator warmup.

    Raises
    ------
    NoDataError: If no price data is available for the requested range.
    """
    load_start = start_date - timedelta(days=warmup_days)
    data = load_stock(stock_id, load_start, end_date, token=token)

    if data.daily.empty:
        raise NoDataError(f"No price data found for {stock_id}.")

    loaded_start = data.daily["date"].min()
    loaded_end   = data.daily["date"].max()

    trades  = run_backtest(data, analysis_start_date=start_date)
    metrics = summarize_backtest(trades)

    return BacktestResult(
        trades=trades,
        metrics=metrics,
        requested_start=start_date,
        requested_end=end_date,
        loaded_start=loaded_start,
        loaded_end=loaded_end,
    )
