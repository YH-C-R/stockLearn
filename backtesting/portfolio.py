"""Multi-stock portfolio backtesting engine.

Simulates equal-capital allocation across a ranked set of signals,
with fixed holding periods and daily rebalancing.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd


@dataclass
class PortfolioConfig:
    """Configuration for run_portfolio_backtest().

    Attributes
    ----------
    holding_days    : Number of trading days to hold each position.
    top_n           : Maximum number of stocks to hold simultaneously.
    min_score       : Only signals with final_score >= this are traded.
    buy_on_next_day : If True, enter on the trading day after the signal date.
    initial_capital : Starting capital (used for equity curve calculation).
    """
    holding_days: int     = 5
    top_n: int            = 5
    min_score: float      = 0.0
    buy_on_next_day: bool = True
    initial_capital: float = 1_000_000.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_portfolio_backtest(
    price_df: pd.DataFrame,
    ranked_signals: pd.DataFrame,
    config: Optional[PortfolioConfig] = None,
) -> tuple[pd.DataFrame, dict]:
    """Run a multi-stock fixed-holding-period portfolio backtest.

    Each day's top-N signals are treated as a new equal-weight basket.
    Positions are opened on the next trading day and closed after
    holding_days trading days.

    Parameters
    ----------
    price_df       : DataFrame with columns ``stock_id``, ``date``, ``close``.
    ranked_signals : DataFrame produced by rank_signals() with columns
                     ``date``, ``stock_id``, ``final_score``, ``rank``.
                     Only rows with rank <= top_n and score >= min_score are used.
    config         : PortfolioConfig. Defaults to PortfolioConfig().

    Returns
    -------
    trades  : DataFrame — one row per completed trade with columns:
              signal_date, stock_id, entry_date, exit_date,
              entry_price, exit_price, return_pct, score.
    metrics : dict — portfolio-level summary statistics.

    Raises
    ------
    ValueError : If required columns are missing.
    """
    if config is None:
        config = PortfolioConfig()

    _validate_inputs(price_df, ranked_signals)

    price_df       = _normalise_dates(price_df.copy())
    ranked_signals = _normalise_dates(ranked_signals.copy())

    # Build lookup structures from price data
    all_stocks    = price_df["stock_id"].unique()
    trading_dates = sorted(price_df["date"].unique())
    if not trading_dates:
        return _empty_trades(), _empty_metrics()

    date_index: dict[date, int] = {d: i for i, d in enumerate(trading_dates)}

    # close_map[(stock_id, date)] → close price
    close_map: dict[tuple, float] = {
        (row.stock_id, row.date): row.close
        for row in price_df.itertuples(index=False)
    }

    # Filter signals
    qualified = ranked_signals[
        (ranked_signals["rank"] <= config.top_n) &
        (ranked_signals["final_score"] >= config.min_score)
    ].copy()

    if qualified.empty:
        return _empty_trades(), _empty_metrics()

    rows = []
    for sig in qualified.itertuples(index=False):
        signal_date: date = sig.date
        stock_id: str     = sig.stock_id

        # Determine entry date
        if config.buy_on_next_day:
            entry_date = _next_trading_date(signal_date, trading_dates, date_index)
        else:
            entry_date = signal_date if signal_date in date_index else None

        if entry_date is None:
            continue

        entry_idx = date_index[entry_date]
        exit_idx  = entry_idx + config.holding_days
        if exit_idx >= len(trading_dates):
            continue  # not enough data to complete the hold

        exit_date    = trading_dates[exit_idx]
        entry_price  = close_map.get((stock_id, entry_date))
        exit_price   = close_map.get((stock_id, exit_date))

        if entry_price is None or exit_price is None or entry_price == 0:
            continue

        return_pct = (exit_price - entry_price) / entry_price * 100

        rows.append({
            "signal_date":  signal_date,
            "stock_id":     stock_id,
            "entry_date":   entry_date,
            "exit_date":    exit_date,
            "entry_price":  round(entry_price, 2),
            "exit_price":   round(exit_price, 2),
            "return_pct":   round(return_pct, 4),
            "score":        sig.final_score,
        })

    if not rows:
        return _empty_trades(), _empty_metrics()

    trades  = pd.DataFrame(rows).sort_values(["entry_date", "stock_id"]).reset_index(drop=True)
    metrics = _compute_metrics(trades, config)
    return trades, metrics


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _compute_metrics(trades: pd.DataFrame, config: PortfolioConfig) -> dict:
    returns = trades["return_pct"]
    n       = len(trades)

    # Portfolio equity curve: group by entry_date, average returns within each day basket
    daily_avg = (
        trades.groupby("entry_date")["return_pct"]
        .mean()
        .sort_index()
    )

    cumulative = ((1 + daily_avg / 100).prod() - 1) * 100
    max_dd     = _max_drawdown(daily_avg)

    # Per-stock win rate uses individual trade results
    win_rate = (returns > 0).sum() / n * 100

    return {
        "num_trades":            n,
        "num_trading_days":      int(daily_avg.shape[0]),
        "win_rate_pct":          round(win_rate, 2),
        "avg_return_pct":        round(returns.mean(), 4),
        "cumulative_return_pct": round(cumulative, 4),
        "max_drawdown_pct":      round(max_dd, 4),
    }


def _max_drawdown(daily_returns_pct: pd.Series) -> float:
    """Maximum peak-to-trough drawdown across the equity curve."""
    if daily_returns_pct.empty:
        return 0.0
    equity = (1 + daily_returns_pct / 100).cumprod()
    peak   = equity.cummax()
    dd     = (equity - peak) / peak * 100
    return float(dd.min())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_inputs(price_df: pd.DataFrame, ranked_signals: pd.DataFrame) -> None:
    for col in ("stock_id", "date", "close"):
        if col not in price_df.columns:
            raise ValueError(f"price_df missing required column: '{col}'")
    for col in ("date", "stock_id", "final_score", "rank"):
        if col not in ranked_signals.columns:
            raise ValueError(f"ranked_signals missing required column: '{col}'")


def _normalise_dates(df: pd.DataFrame) -> pd.DataFrame:
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _next_trading_date(
    signal_date: date,
    trading_dates: list[date],
    date_index: dict[date, int],
) -> Optional[date]:
    idx = date_index.get(signal_date)
    if idx is not None:
        next_idx = idx + 1
    else:
        next_idx = next(
            (i for i, d in enumerate(trading_dates) if d > signal_date),
            None,
        )
        if next_idx is None:
            return None

    return trading_dates[next_idx] if next_idx < len(trading_dates) else None


def _empty_trades() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "signal_date", "stock_id", "entry_date", "exit_date",
        "entry_price", "exit_price", "return_pct", "score",
    ])


def _empty_metrics() -> dict:
    return {
        "num_trades":            0,
        "num_trading_days":      0,
        "win_rate_pct":          0.0,
        "avg_return_pct":        0.0,
        "cumulative_return_pct": 0.0,
        "max_drawdown_pct":      0.0,
    }
