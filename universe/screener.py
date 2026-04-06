"""Universe screener — filter stocks before running strategies.

Usage
-----
    from universe.screener import ScreenerConfig, screen

    config = ScreenerConfig(min_avg_volume=1_000_000, min_price=10.0)
    screened_ids = screen(price_df, config)
"""

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class ScreenerConfig:
    """Criteria for filtering the trading universe.

    Attributes
    ----------
    min_avg_volume  : Minimum average daily volume over the lookback window.
                      Stocks below this are excluded (liquidity filter).
    min_price       : Minimum closing price. Excludes penny stocks.
    max_price       : Maximum closing price. Set to None to disable.
    volume_window   : Lookback window (trading days) for average volume calculation.
    exclude_ids     : Explicit list of stock_ids to always exclude.
    """
    min_avg_volume: float        = 500_000.0
    min_price: float             = 10.0
    max_price: Optional[float]   = None
    volume_window: int           = 20
    exclude_ids: list[str]       = field(default_factory=list)


def screen(
    price_df: pd.DataFrame,
    config: Optional[ScreenerConfig] = None,
) -> list[str]:
    """Filter a stock universe based on price and volume criteria.

    Uses the most recent ``volume_window`` trading days of price data
    to calculate average volume per stock, then applies all active filters.

    Parameters
    ----------
    price_df : DataFrame with columns ``stock_id``, ``date``, ``close``, ``volume``.
               Must contain data for at least one stock.
    config   : ScreenerConfig. Defaults to ScreenerConfig().

    Returns
    -------
    List of stock_id strings that pass all filters, sorted alphabetically.

    Raises
    ------
    ValueError : If required columns are missing from price_df.
    """
    if config is None:
        config = ScreenerConfig()

    _validate_columns(price_df)

    df = price_df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date

    # Use the most recent volume_window rows per stock to compute avg_volume
    df = df.sort_values(["stock_id", "date"])
    # groupby().tail() preserves columns in pandas 2.x (unlike apply)
    recent = df.groupby("stock_id").tail(config.volume_window)

    summary = recent.groupby("stock_id").agg(
        avg_volume=("volume", "mean"),
        last_close=("close", "last"),
    ).reset_index()

    # Apply filters
    mask = pd.Series([True] * len(summary), index=summary.index)

    mask &= summary["avg_volume"] >= config.min_avg_volume
    mask &= summary["last_close"] >= config.min_price

    if config.max_price is not None:
        mask &= summary["last_close"] <= config.max_price

    if config.exclude_ids:
        mask &= ~summary["stock_id"].isin(config.exclude_ids)

    result = summary.loc[mask, "stock_id"].sort_values().tolist()
    return result


def screen_df(
    price_df: pd.DataFrame,
    config: Optional[ScreenerConfig] = None,
) -> pd.DataFrame:
    """Same as screen() but returns a summary DataFrame instead of a plain list.

    Returns
    -------
    DataFrame with columns: stock_id, avg_volume, last_close.
    Sorted by avg_volume descending.
    """
    if config is None:
        config = ScreenerConfig()

    _validate_columns(price_df)

    df = price_df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values(["stock_id", "date"])

    # groupby().tail() preserves columns in pandas 2.x (unlike apply)
    recent = df.groupby("stock_id").tail(config.volume_window)

    summary = recent.groupby("stock_id").agg(
        avg_volume=("volume", "mean"),
        last_close=("close", "last"),
    ).reset_index()

    mask = pd.Series([True] * len(summary), index=summary.index)
    mask &= summary["avg_volume"] >= config.min_avg_volume
    mask &= summary["last_close"] >= config.min_price

    if config.max_price is not None:
        mask &= summary["last_close"] <= config.max_price

    if config.exclude_ids:
        mask &= ~summary["stock_id"].isin(config.exclude_ids)

    return (
        summary[mask]
        .sort_values("avg_volume", ascending=False)
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_columns(price_df: pd.DataFrame) -> None:
    required = {"stock_id", "date", "close", "volume"}
    missing  = required - set(price_df.columns)
    if missing:
        raise ValueError(f"price_df missing required columns: {missing}")
