"""Simple fixed-holding-period backtesting engine.

Assumes long-only trades, one position per signal, no portfolio management.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd


@dataclass
class BacktestConfig:
    """Configuration for run_simple_backtest().

    Attributes
    ----------
    holding_days    : Number of trading days to hold after entry.
    min_score       : Only signals with score >= this threshold are traded.
    buy_on_next_day : If True, enter on the trading day after the signal date.
                      If False, enter on the signal date itself (lookahead — use
                      only for research).
    """
    holding_days: int   = 5
    min_score: float    = 0.8
    buy_on_next_day: bool = True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_simple_backtest(
    price_df: pd.DataFrame,
    signals_df: pd.DataFrame,
    config: Optional[BacktestConfig] = None,
) -> tuple[pd.DataFrame, dict]:
    """Run a fixed-holding-period backtest.

    Parameters
    ----------
    price_df : DataFrame with at least columns ``date`` and ``close``.
               ``date`` may be datetime or date objects.
    signals_df : DataFrame with at least columns ``date`` and ``score``.
                 ``date`` may be datetime or date objects.
    config   : BacktestConfig instance. Defaults to BacktestConfig().

    Returns
    -------
    trades : DataFrame — one row per completed trade with columns:
             signal_date, entry_date, exit_date,
             entry_price, exit_price, holding_days, return_pct.
    metrics : dict — summary statistics for the full trade set.

    Raises
    ------
    ValueError : If required columns are missing from either DataFrame.
    """
    if config is None:
        config = BacktestConfig()

    _validate_inputs(price_df, signals_df)

    price_df    = _normalise_dates(price_df.copy())
    signals_df  = _normalise_dates(signals_df.copy())

    # Sorted array of all available trading dates
    trading_dates: list[date] = sorted(price_df["date"].unique())
    if not trading_dates:
        return _empty_trades(), _empty_metrics()

    close_map: dict[date, float] = price_df.set_index("date")["close"].to_dict()
    date_index: dict[date, int]  = {d: i for i, d in enumerate(trading_dates)}

    # Filter signals by min_score
    qualified = signals_df[signals_df["score"] >= config.min_score].copy()
    qualified = qualified.sort_values("date").drop_duplicates(subset="date")

    if qualified.empty:
        return _empty_trades(), _empty_metrics()

    rows = []
    for signal_row in qualified.itertuples(index=False):
        signal_date: date = signal_row.date

        # Determine entry date
        if config.buy_on_next_day:
            entry_date = _next_trading_date(signal_date, trading_dates, date_index)
        else:
            entry_date = signal_date if signal_date in date_index else None

        if entry_date is None:
            continue  # signal too close to end of data

        # Determine exit date (entry + holding_days trading days)
        entry_idx = date_index[entry_date]
        exit_idx  = entry_idx + config.holding_days
        if exit_idx >= len(trading_dates):
            continue  # not enough data to complete the hold

        exit_date    = trading_dates[exit_idx]
        entry_price  = close_map.get(entry_date)
        exit_price   = close_map.get(exit_date)

        if entry_price is None or exit_price is None or entry_price == 0:
            continue  # missing price data

        return_pct = (exit_price - entry_price) / entry_price * 100

        rows.append({
            "signal_date":  signal_date,
            "entry_date":   entry_date,
            "exit_date":    exit_date,
            "entry_price":  round(entry_price, 2),
            "exit_price":   round(exit_price, 2),
            "holding_days": config.holding_days,
            "return_pct":   round(return_pct, 4),
        })

    if not rows:
        return _empty_trades(), _empty_metrics()

    trades  = pd.DataFrame(rows)
    metrics = _compute_metrics(trades)
    return trades, metrics


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _compute_metrics(trades: pd.DataFrame) -> dict:
    returns = trades["return_pct"]
    n       = len(trades)

    cumulative = ((1 + returns / 100).prod() - 1) * 100
    max_dd     = _max_drawdown(returns)

    return {
        "num_trades":        n,
        "win_rate_pct":      round((returns > 0).sum() / n * 100, 2),
        "avg_return_pct":    round(returns.mean(), 4),
        "cumulative_return_pct": round(cumulative, 4),
        "max_drawdown_pct":  round(max_dd, 4),
    }


def _max_drawdown(returns_pct: pd.Series) -> float:
    """Maximum peak-to-trough drawdown across the equity curve."""
    equity = (1 + returns_pct / 100).cumprod()
    peak   = equity.cummax()
    dd     = (equity - peak) / peak * 100
    return float(dd.min())   # negative value; 0.0 if no drawdown


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_inputs(price_df: pd.DataFrame, signals_df: pd.DataFrame) -> None:
    for col in ("date", "close"):
        if col not in price_df.columns:
            raise ValueError(f"price_df missing required column: '{col}'")
    for col in ("date", "score"):
        if col not in signals_df.columns:
            raise ValueError(f"signals_df missing required column: '{col}'")


def _normalise_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce the date column to datetime.date objects."""
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _next_trading_date(
    signal_date: date,
    trading_dates: list[date],
    date_index: dict[date, int],
) -> Optional[date]:
    """Return the first trading date strictly after signal_date, or None."""
    idx = date_index.get(signal_date)
    if idx is not None:
        next_idx = idx + 1
    else:
        # signal_date is not itself a trading day (weekend/holiday) — find
        # the next trading day that comes after it
        next_idx = next(
            (i for i, d in enumerate(trading_dates) if d > signal_date),
            None,
        )
        if next_idx is None:
            return None

    return trading_dates[next_idx] if next_idx < len(trading_dates) else None


def _empty_trades() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "signal_date", "entry_date", "exit_date",
        "entry_price", "exit_price", "holding_days", "return_pct",
    ])


def _empty_metrics() -> dict:
    return {
        "num_trades":            0,
        "win_rate_pct":          0.0,
        "avg_return_pct":        0.0,
        "cumulative_return_pct": 0.0,
        "max_drawdown_pct":      0.0,
    }
