"""Load and prepare all data for a single stock.

Fetches price, margin, and EPS data, aligns them to a daily index,
and computes PE ratio where possible.

Usage
-----
    from data.single_stock_loader import load_stock, StockData

    data = load_stock("2330", date(2023, 1, 1), date(2023, 12, 31), token=TOKEN)
    print(data.daily.head())
    print(data.summary())
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd

from data.fetchers.fundamentals import fetch_eps_data
from data.fetchers.margin import fetch_margin_data
from data.fetchers.price import fetch_daily_price

logger = logging.getLogger(__name__)

# EPS is published ~45 days after quarter end; fetch extra history so the
# first daily rows have a valid forward-filled EPS value.
_EPS_LOOKBACK_DAYS = 400


@dataclass
class StockData:
    """All data for a single stock aligned to a daily index.

    Attributes
    ----------
    stock_id  : Stock identifier.
    start_date: Requested start date.
    end_date  : Requested end date.
    daily     : Daily DataFrame with columns:
                  date, close, volume,
                  margin_purchase_balance (NaN if unavailable),
                  eps (forward-filled from quarterly reports, NaN if unavailable),
                  pe  (close / eps, NaN where either is missing or eps <= 0).
    warnings  : List of non-fatal issues encountered during loading.
    """
    stock_id:   str
    start_date: date
    end_date:   date
    daily:      pd.DataFrame
    warnings:   list[str] = field(default_factory=list)

    def summary(self) -> dict:
        """Return a quick overview of data availability."""
        df = self.daily
        if df.empty:
            return {"stock_id": self.stock_id, "rows": 0}
        return {
            "stock_id":          self.stock_id,
            "rows":              len(df),
            "date_range":        (df["date"].min(), df["date"].max()),
            "price_coverage":    f"{df['close'].notna().sum()}/{len(df)}",
            "margin_coverage":   f"{df['margin_purchase_balance'].notna().sum()}/{len(df)}",
            "eps_coverage":      f"{df['eps'].notna().sum()}/{len(df)}",
            "pe_coverage":       f"{df['pe'].notna().sum()}/{len(df)}",
            "warnings":          self.warnings,
        }


def load_stock(
    stock_id:   str,
    start_date: date,
    end_date:   date,
    token:      Optional[str] = None,
) -> StockData:
    """Fetch and align all data for a single stock.

    Parameters
    ----------
    stock_id   : Taiwan stock ticker (e.g. "2330").
    start_date : First date of the requested window.
    end_date   : Last date of the requested window.
    token      : FinMind API token.  Pass None to use the anonymous limit.

    Returns
    -------
    StockData with a ``daily`` DataFrame ready for analysis.
    Missing data series result in NaN columns, not exceptions.
    """
    warnings: list[str] = []

    # ── 1. Price (required) ───────────────────────────────────────────────────
    try:
        price_df = fetch_daily_price(stock_id, start_date, end_date, token=token)
    except Exception as exc:
        logger.error("price fetch failed for %s: %s", stock_id, exc)
        return StockData(
            stock_id=stock_id,
            start_date=start_date,
            end_date=end_date,
            daily=pd.DataFrame(),
            warnings=[f"price fetch failed: {exc}"],
        )

    if price_df.empty:
        return StockData(
            stock_id=stock_id,
            start_date=start_date,
            end_date=end_date,
            daily=pd.DataFrame(),
            warnings=["price data returned empty"],
        )

    # Build the daily spine from price data
    daily = (
        price_df[["date", "close", "volume"]]
        .copy()
        .sort_values("date")
        .reset_index(drop=True)
    )
    daily["date"] = pd.to_datetime(daily["date"]).dt.date

    # ── 2. Margin (optional) ──────────────────────────────────────────────────
    try:
        margin_df = fetch_margin_data(stock_id, start_date, end_date, token=token)
        if not margin_df.empty:
            margin_df["date"] = pd.to_datetime(margin_df["date"]).dt.date
            margin_col = margin_df[["date", "margin_purchase_balance"]]
            daily = daily.merge(margin_col, on="date", how="left")
        else:
            daily["margin_purchase_balance"] = float("nan")
            warnings.append("margin data returned empty")
    except Exception as exc:
        logger.warning("margin fetch failed for %s: %s", stock_id, exc)
        daily["margin_purchase_balance"] = float("nan")
        warnings.append(f"margin fetch failed: {exc}")

    # ── 3. EPS (optional) — forward-fill quarterly to daily ──────────────────
    try:
        # Fetch from earlier to ensure the first daily rows have a valid EPS
        eps_start = _shift_date(start_date, -_EPS_LOOKBACK_DAYS)
        eps_df = fetch_eps_data(stock_id, eps_start, end_date, token=token)

        if not eps_df.empty:
            eps_daily = _align_eps_to_daily(eps_df, daily["date"])
            daily = daily.merge(eps_daily, on="date", how="left")
        else:
            daily["eps"] = float("nan")
            warnings.append("EPS data returned empty")
    except Exception as exc:
        logger.warning("EPS fetch failed for %s: %s", stock_id, exc)
        daily["eps"] = float("nan")
        warnings.append(f"EPS fetch failed: {exc}")

    # ── 4. PE ratio ───────────────────────────────────────────────────────────
    daily["pe"] = _compute_pe(daily["close"], daily["eps"])

    # ── 5. Ensure column order ────────────────────────────────────────────────
    cols = ["date", "close", "volume", "margin_purchase_balance", "eps", "pe"]
    daily = daily[cols].reset_index(drop=True)

    return StockData(
        stock_id=stock_id,
        start_date=start_date,
        end_date=end_date,
        daily=daily,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _align_eps_to_daily(eps_df: pd.DataFrame, dates: pd.Series) -> pd.DataFrame:
    """Forward-fill quarterly EPS onto a daily date spine.

    Uses the ``effective_date`` column if present (set by fetch_eps_data),
    otherwise falls back to ``report_period``.  Each quarter's EPS is
    first visible on its effective date and persists until the next quarter.

    Returns a DataFrame with columns ``date`` and ``eps``.
    """
    from strategies.davis_double import _effective_date  # reuse existing logic

    eps = eps_df.copy()

    # Compute effective date (when EPS becomes known to the market)
    if "effective_date" not in eps.columns:
        eps["effective_date"] = eps.apply(_effective_date, axis=1)

    eps["effective_date"] = pd.to_datetime(eps["effective_date"]).dt.date
    eps = eps.sort_values("effective_date")

    # Build a date → eps mapping via merge_asof (backward fill)
    daily_spine = pd.DataFrame({"date": sorted(dates)})
    daily_spine["date_ts"] = pd.to_datetime(daily_spine["date"])
    eps["eff_ts"] = pd.to_datetime(eps["effective_date"])

    merged = pd.merge_asof(
        daily_spine.sort_values("date_ts"),
        eps[["eff_ts", "eps"]].sort_values("eff_ts"),
        left_on="date_ts",
        right_on="eff_ts",
        direction="backward",
    )

    return merged[["date", "eps"]].reset_index(drop=True)


def _compute_pe(close: pd.Series, eps: pd.Series) -> pd.Series:
    """Compute trailing PE = close / eps.  NaN where eps is missing or <= 0."""
    pe = close / eps
    pe[eps <= 0] = float("nan")
    return pe.round(2)


def _shift_date(d: date, days: int) -> date:
    """Return d shifted by `days` calendar days (negative = earlier)."""
    from datetime import timedelta
    return d + timedelta(days=days)
