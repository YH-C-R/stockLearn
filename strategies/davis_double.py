"""Davis Double strategy — one signal per quarter, on the earnings release date.

Signal logic (all three conditions must be true):
  1. EPS YoY growth > yoy_threshold (default 30%)
  2. Close price > MA (PE expansion proxy)
  3. Distance from MA <= max_ma_distance (avoids overextended entries)

Signal frequency:
  At most ONE signal per stock per quarter.
  The trigger date is the first trading day on or after effective_date
  (release_date if available, else report_period + 45/90 day fallback).
  If conditions are not met on that day, no signal is emitted for that quarter.

Score:
  Exponential curve from BASE=0.5 (at threshold) asymptotically approaching 1.0.
  score = 0.5 + 0.5 * (1 - e^(-decay * excess))   where excess = yoy_growth - threshold

  Growth tier examples (threshold=30%, decay=3.0):
    30%  borderline  → 0.50
    40%  moderate    → 0.64
    50%  solid       → 0.74
   100%  strong      → 0.93
   200%  exceptional → ~1.00
"""

import math
from datetime import timedelta

import pandas as pd

from signals.base import Signal, make_signal
from strategies.base import BaseStrategy

_REQUIRED_PRICE_COLS = ["stock_id", "date", "close"]
_REQUIRED_FUND_COLS  = ["stock_id", "report_period", "eps"]

# Conservative release-date fallbacks (days after quarter end)
_DEFAULT_RELEASE_OFFSET = 45
_Q4_RELEASE_OFFSET      = 90


class DavisDoubleStrategy(BaseStrategy):
    """One signal per quarter: EPS YoY > threshold AND close > MA (within distance).

    Parameters
    ----------
    ma_window       : Lookback window for the MA price proxy (days).
    yoy_threshold   : Minimum YoY EPS growth to qualify (default 0.30 = 30%).
    max_ma_distance : Maximum allowed distance above MA as a fraction of MA.
                      Skips overextended entries. Default 0.15 = 15%.
                      distance_to_ma = (close - ma) / ma
    """

    name = "davis_double"

    def __init__(
        self,
        ma_window: int         = 60,
        yoy_threshold: float   = 0.30,   # 30% YoY EPS growth required
        max_ma_distance: float = 0.15,   # skip if price > 15% above MA
    ) -> None:
        self.ma_window       = ma_window
        self.yoy_threshold   = yoy_threshold
        self.max_ma_distance = max_ma_distance

    def generate(
        self,
        price_df: pd.DataFrame,
        *,
        fundamentals_df: pd.DataFrame,
        **kwargs: pd.DataFrame,
    ) -> list[Signal]:
        """Return at most one signal per stock per quarter.

        Parameters
        ----------
        price_df        : Daily OHLCV DataFrame (stock_id, date, close, …).
        fundamentals_df : Quarterly EPS DataFrame from fetch_eps_data()
                          (stock_id, report_period, eps, release_date optional).
        """
        self.validate_columns(price_df,        _REQUIRED_PRICE_COLS, "price_df")
        self.validate_columns(fundamentals_df, _REQUIRED_FUND_COLS,  "fundamentals_df")

        price_df        = price_df.copy()
        fundamentals_df = fundamentals_df.copy()

        price_df["date"]                 = pd.to_datetime(price_df["date"]).dt.date
        fundamentals_df["report_period"] = pd.to_datetime(
            fundamentals_df["report_period"]
        ).dt.date

        # Add effective_date and YoY growth to each quarter row
        fundamentals_df["effective_date"] = fundamentals_df.apply(_effective_date, axis=1)
        fundamentals_df = _add_yoy_growth(fundamentals_df)

        # Pre-compute MA on the price series (need full history for rolling)
        price_df = price_df.sort_values(["stock_id", "date"]).reset_index(drop=True)
        price_df["ma"] = price_df.groupby("stock_id")["close"].transform(
            lambda x: x.rolling(self.ma_window, min_periods=self.ma_window).mean()
        )

        # Build a date → (close, ma) lookup per stock for fast access
        price_lookup: dict[str, dict] = {
            sid: grp.set_index("date")[["close", "ma"]].to_dict("index")
            for sid, grp in price_df.groupby("stock_id")
        }
        # Sorted trading dates per stock for finding "first day >= effective_date"
        trading_dates: dict[str, list] = {
            sid: sorted(grp["date"].tolist())
            for sid, grp in price_df.groupby("stock_id")
        }

        signals: list[Signal] = []

        for row in fundamentals_df.itertuples(index=False):
            if pd.isna(row.yoy_growth):
                continue  # insufficient history for YoY (first year)

            # Condition 1: EPS YoY growth must exceed threshold
            if row.yoy_growth <= self.yoy_threshold:
                continue

            stock_id      = row.stock_id
            effective_dt  = row.effective_date
            dates         = trading_dates.get(stock_id, [])
            lookup        = price_lookup.get(stock_id, {})

            # Find the first trading day on or after effective_date
            trigger_date = next((d for d in dates if d >= effective_dt), None)
            if trigger_date is None:
                continue  # effective_date is beyond available price data

            price_row = lookup.get(trigger_date)
            if price_row is None:
                continue

            close = price_row["close"]
            ma    = price_row["ma"]

            if pd.isna(ma):
                continue  # not enough history for MA on this date

            distance_to_ma = (close - ma) / ma

            # Condition 2: price must be above MA (PE expansion proxy)
            if distance_to_ma <= 0:
                continue

            # Condition 3: price must not be overextended above MA
            if distance_to_ma > self.max_ma_distance:
                continue

            score = _growth_score(row.yoy_growth, self.yoy_threshold)

            signals.append(make_signal(
                stock_id=stock_id,
                date=trigger_date,
                signal_name=self.name,
                signal_value=round(row.eps, 4),
                score=score,
                metadata={
                    "close":              round(close, 2),
                    "ma":                 round(ma, 2),
                    "eps":                round(row.eps, 4),
                    "yoy_growth_pct":     round(row.yoy_growth * 100, 2),
                    "yoy_excess_pct":     round((row.yoy_growth - self.yoy_threshold) * 100, 2),
                    "distance_to_ma_pct": round(distance_to_ma * 100, 2),
                    "report_period":      str(row.report_period),
                    "effective_date":     str(effective_dt),
                    "trigger_date":       str(trigger_date),
                    "yoy_threshold":      self.yoy_threshold,
                    "max_ma_distance":    self.max_ma_distance,
                    "ma_window":          self.ma_window,
                },
            ))

        return signals


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _growth_score(yoy_growth: float, threshold: float, decay: float = 3.0) -> float:
    """Map YoY EPS growth to a score in [0.5, 1.0) using an exponential curve.

    Formula
    -------
        excess = yoy_growth - threshold
        score  = 0.5 + 0.5 * (1 - e^(-decay * excess))

    BASE = 0.5 means a borderline signal (growth just at threshold) scores 0.5,
    leaving the lower half of [0, 1] unused by this strategy — reflecting that
    even the minimum qualifying signal is meaningfully bullish, not neutral.

    The curve is asymptotic: score approaches 1.0 but never reaches it, so
    exceptional growth is always distinguishable from merely strong growth.

    Tiers with threshold=0.30, decay=3.0
    --------------------------------------
        30%  borderline  → 0.50
        40%  moderate    → 0.64
        50%  solid       → 0.74
       100%  strong      → 0.93
       200%  exceptional → ~1.00

    Parameters
    ----------
    yoy_growth : Actual YoY EPS growth (decimal, e.g. 0.35 = 35%).
    threshold  : Minimum qualifying growth (same unit).
    decay      : Curve steepness. Higher = faster rise toward 1.0.
    """
    BASE = 0.5
    excess = max(0.0, yoy_growth - threshold)
    score  = BASE + (1.0 - BASE) * (1.0 - math.exp(-decay * excess))
    return round(score, 4)


# ---------------------------------------------------------------------------
# Module-level alignment helpers (reusable by other strategies)
# ---------------------------------------------------------------------------

def _effective_date(row: pd.Series) -> "date":
    """Return the date after which this quarter's EPS is publicly known."""
    from datetime import date as date_type
    release = row.get("release_date")
    if pd.notna(release) and release is not None:
        return release
    period = row["report_period"]
    offset = _Q4_RELEASE_OFFSET if period.month == 12 else _DEFAULT_RELEASE_OFFSET
    return period + timedelta(days=offset)


def _add_yoy_growth(fund_df: pd.DataFrame) -> pd.DataFrame:
    """Add yoy_growth column: (current EPS - same Q last year) / |same Q last year|."""
    fund_df = fund_df.sort_values(["stock_id", "report_period"]).copy()
    fund_df["eps_yoy"]   = fund_df.groupby("stock_id")["eps"].transform(lambda x: x.shift(4))
    fund_df["yoy_growth"] = (fund_df["eps"] - fund_df["eps_yoy"]) / fund_df["eps_yoy"].abs()
    return fund_df


def _align_to_daily(
    price_df: pd.DataFrame,
    fund_df: pd.DataFrame,
) -> pd.DataFrame:
    """Forward-fill quarterly EPS onto daily price rows without lookahead."""
    price_dt = price_df.copy()
    price_dt["date"] = pd.to_datetime(price_dt["date"])
    price_dt = price_dt.sort_values(["stock_id", "date"])

    fund_dt = fund_df[["stock_id", "effective_date", "report_period", "eps", "yoy_growth"]].copy()
    fund_dt = fund_dt.rename(columns={"effective_date": "date"})
    fund_dt["date"] = pd.to_datetime(fund_dt["date"])
    fund_dt = fund_dt.sort_values(["stock_id", "date"])

    merged = pd.merge_asof(
        price_dt,
        fund_dt,
        on="date",
        by="stock_id",
        direction="backward",   # last known EPS whose effective_date <= trading date
    )

    # Restore date to datetime.date
    merged["date"] = merged["date"].dt.date
    return merged
