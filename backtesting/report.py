"""Display helpers for backtest results.

All functions print to stdout and return None.
No business logic — formatting only.

Usage
-----
    from backtesting.report import (
        print_backtest_summary,
        print_trade_sample,
        print_selected_stocks,
        print_per_stock_summary,
    )
"""

import pandas as pd


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def print_backtest_summary(metrics: dict) -> None:
    """Print the standard five portfolio metrics in a fixed-width table.

    Parameters
    ----------
    metrics : dict produced by compute_trade_metrics() or run_portfolio_backtest().
              Expected keys: num_trades, win_rate_pct, avg_return_pct,
              cumulative_return_pct, max_drawdown_pct.
              Unknown keys are silently ignored; missing keys show as 'N/A'.
    """
    def _get(key: str, fmt: str) -> str:
        val = metrics.get(key)
        if val is None:
            return "N/A"
        try:
            return format(val, fmt)
        except (TypeError, ValueError):
            return str(val)

    rows = [
        ("Trades",            _get("num_trades",            "d")),
        ("Win rate",          _get("win_rate_pct",          ".1f") + "%"),
        ("Avg return",        _get("avg_return_pct",        "+.2f") + "%"),
        ("Cumulative return", _get("cumulative_return_pct", "+.2f") + "%"),
        ("Max drawdown",      _get("max_drawdown_pct",      ".2f") + "%"),
    ]

    # Optional extra fields present in portfolio metrics
    if "num_trading_days" in metrics:
        rows.insert(1, ("Trading days", _get("num_trading_days", "d")))

    label_w = max(len(r[0]) for r in rows) + 2
    print()
    for label, value in rows:
        print(f"  {label:<{label_w}}: {value}")
    print()


def print_trade_sample(trades_df: pd.DataFrame, n: int = 10) -> None:
    """Print the first N rows of a trades DataFrame.

    Parameters
    ----------
    trades_df : Output of run_simple_backtest() or run_portfolio_backtest().
    n         : Maximum number of rows to display.
    """
    if trades_df.empty:
        print("  (no trades to display)\n")
        return

    # Preferred column order — show only columns that actually exist
    preferred = [
        "signal_date", "stock_id", "entry_date", "exit_date",
        "entry_price", "exit_price", "return_pct", "score",
        "holding_days",
    ]
    cols = [c for c in preferred if c in trades_df.columns]
    # Append any remaining columns not in the preferred list
    cols += [c for c in trades_df.columns if c not in cols]

    sample = trades_df[cols].head(n)
    print()
    print(sample.to_string(index=False))
    if len(trades_df) > n:
        print(f"  … {len(trades_df) - n} more rows not shown")
    print()


def print_selected_stocks(
    selection_df: pd.DataFrame,
    last_n_dates: int = 5,
) -> None:
    """Print ranked stock selections for the most recent signal dates.

    Parameters
    ----------
    selection_df  : Output of rank_signals() with columns
                    date, stock_id, final_score, rank.
    last_n_dates  : How many of the most recent dates to display.
    """
    if selection_df.empty:
        print("  (no selections to display)\n")
        return

    required = {"date", "stock_id", "final_score", "rank"}
    missing  = required - set(selection_df.columns)
    if missing:
        raise ValueError(f"print_selected_stocks: DataFrame missing columns: {missing}")

    latest_dates = sorted(selection_df["date"].unique())[-last_n_dates:]
    subset = selection_df[selection_df["date"].isin(latest_dates)].copy()

    print()
    print(f"  {'date':<12}  {'rank':>4}  {'stock_id':>10}  {'final_score':>12}")
    print("  " + "─" * 44)

    prev = None
    for row in subset.sort_values(["date", "rank"]).itertuples(index=False):
        if prev is not None and row.date != prev:
            print()
        print(
            f"  {str(row.date):<12}  {row.rank:>4}"
            f"  {row.stock_id:>10}  {row.final_score:>12.4f}"
        )
        prev = row.date
    print()


def print_per_stock_summary(trades_df: pd.DataFrame) -> None:
    """Print a per-stock breakdown of trade count, avg return, and win rate.

    Parameters
    ----------
    trades_df : Output of run_portfolio_backtest(). Must contain columns
                stock_id and return_pct.
    """
    if trades_df.empty:
        print("  (no trades to summarise)\n")
        return

    summary = (
        trades_df.groupby("stock_id")["return_pct"]
        .agg(
            trades    = "count",
            avg_return= "mean",
            win_rate  = lambda x: (x > 0).mean() * 100,
        )
        .round(2)
        .sort_values("avg_return", ascending=False)
        .reset_index()
    )

    print()
    print(summary.to_string(index=False))
    print()
