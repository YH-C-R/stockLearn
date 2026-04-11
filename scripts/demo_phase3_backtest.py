"""Demo: Phase 3 multi-stock portfolio backtest + parameter sweep.

Pipeline
--------
  1. Fetch price, margin, and fundamentals for a small universe.
  2. Screen stocks by minimum volume / price.
  3. Run CombinedStrategy once (min_final_score=0 to retain all signals).
  4. Single-run backtest with default parameters (for inspection).
  5. Parameter sweep over holding_days × top_n × min_final_score.
  6. Print sweep results sorted by cumulative return.

Run
---
    python3 scripts/demo_phase3_backtest.py
"""

import sys
from datetime import date
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from backtesting.portfolio import PortfolioConfig, run_portfolio_backtest
from backtesting.report import (
    print_backtest_summary,
    print_per_stock_summary,
    print_selected_stocks,
    print_trade_sample,
)
from config.credentials import FINMIND_TOKEN
from data.fetchers.fundamentals import fetch_eps_data
from data.fetchers.margin import fetch_margin_data
from data.fetchers.price import fetch_daily_price
from strategies.combined import CombinedStrategy, CombinedStrategyConfig, rank_signals
from universe.screener import ScreenerConfig, screen

# ---------------------------------------------------------------------------
# Universe & date range
# ---------------------------------------------------------------------------

UNIVERSE = [
    "2330",   # TSMC
    "2317",   # Foxconn
    "2454",   # MediaTek
    "2412",   # Chunghwa Telecom
    "2882",   # Cathay Financial
    "2308",   # Delta Electronics
    "3711",   # ASMedia
    "2357",   # Asustek
]

START_DATE = date(2022, 1, 1)
END_DATE   = date(2022, 12, 31)
FUND_START = date(2020, 1, 1)   # needs ~5 quarters for YoY

# ---------------------------------------------------------------------------
# Default single-run parameters (used for sections 4–8)
# ---------------------------------------------------------------------------

DEFAULT_TOP_N         = 3
DEFAULT_HOLDING_DAYS  = 20
DEFAULT_MIN_SCORE     = 0.3

SCREENER_CONFIG = ScreenerConfig(
    min_avg_volume = 500_000,
    min_price      = 10.0,
    volume_window  = 20,
)

COMBINED_CONFIG = CombinedStrategyConfig(
    mt_cooldown_days    = 10,
    dd_persistence_days = 5,
    min_final_score     = 0.0,   # keep all signals — sweep filters later
)

# ---------------------------------------------------------------------------
# Parameter sweep grid
# ---------------------------------------------------------------------------

SWEEP_HOLDING_DAYS   = [5, 10, 20]
SWEEP_TOP_N          = [3, 5]
SWEEP_MIN_SCORE      = [0.2, 0.3, 0.4]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")


def fetch_all(stock_ids: list[str], token: str | None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    price_frames, margin_frames, fund_frames = [], [], []

    for sid in stock_ids:
        try:
            price_frames.append(fetch_daily_price(sid, START_DATE, END_DATE, token=token))
        except Exception as exc:
            print(f"    price  {sid}: FAILED — {exc}")
        try:
            margin_frames.append(fetch_margin_data(sid, START_DATE, END_DATE, token=token))
        except Exception as exc:
            print(f"    margin {sid}: FAILED — {exc}")
        try:
            fund_frames.append(fetch_eps_data(sid, FUND_START, END_DATE, token=token))
        except Exception as exc:
            print(f"    fund   {sid}: FAILED — {exc}")

    def concat(frames):
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    return concat(price_frames), concat(margin_frames), concat(fund_frames)


def run_sweep(
    full_result: pd.DataFrame,
    price_df: pd.DataFrame,
) -> pd.DataFrame:
    """Run all parameter combinations and return a summary DataFrame."""
    rows = []
    combos = list(product(SWEEP_HOLDING_DAYS, SWEEP_TOP_N, SWEEP_MIN_SCORE))
    print(f"  Running {len(combos)} combinations …")

    for holding_days, top_n, min_score in combos:
        # Filter signals by score threshold, then rank
        filtered = full_result[full_result["final_score"] >= min_score]
        if filtered.empty:
            rows.append({
                "holding_days": holding_days, "top_n": top_n,
                "min_score": min_score, "trades": 0,
                "cum_return_%": 0.0, "win_rate_%": 0.0, "max_dd_%": 0.0,
            })
            continue

        ranked = rank_signals(filtered, top_n=top_n)
        cfg    = PortfolioConfig(
            holding_days    = holding_days,
            top_n           = top_n,
            min_score       = min_score,
            buy_on_next_day = True,
        )
        _, metrics = run_portfolio_backtest(price_df, ranked, cfg)

        rows.append({
            "holding_days":  holding_days,
            "top_n":         top_n,
            "min_score":     min_score,
            "trades":        metrics["num_trades"],
            "cum_return_%":  metrics["cumulative_return_pct"],
            "win_rate_%":    metrics["win_rate_pct"],
            "max_dd_%":      metrics["max_drawdown_pct"],
        })

    return (
        pd.DataFrame(rows)
        .sort_values("cum_return_%", ascending=False)
        .reset_index(drop=True)
    )


def print_sweep_table(sweep_df: pd.DataFrame) -> None:
    """Print the sweep results as a fixed-width table."""
    if sweep_df.empty:
        print("  (no results)\n")
        return

    header = (
        f"  {'hold':>4}  {'top_n':>5}  {'min_sc':>6}  "
        f"{'trades':>6}  {'cum_ret%':>9}  {'win%':>6}  {'max_dd%':>8}"
    )
    print(header)
    print("  " + "─" * (len(header) - 2))

    for row in sweep_df.itertuples(index=False):
        # positional indexing avoids namedtuple issues with "%" in column names
        print(
            f"  {row[0]:>4}  {row[1]:>5}  {row[2]:>6.1f}  "
            f"  {row[3]:>5}  {row[4]:>+9.2f}  {row[5]:>6.1f}  {row[6]:>8.2f}"
        )
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    token = FINMIND_TOKEN or None

    # ── 1. Fetch ──────────────────────────────────────────────────────────────
    section(f"1. Fetching data  ({len(UNIVERSE)} stocks,  {START_DATE} → {END_DATE})")
    price_df, margin_df, fund_df = fetch_all(UNIVERSE, token)
    print(f"  price rows   : {len(price_df)}")
    print(f"  margin rows  : {len(margin_df)}")
    print(f"  fund quarters: {len(fund_df)}")

    if price_df.empty:
        print("\n  No price data — aborting.")
        return

    # ── 2. Screen ─────────────────────────────────────────────────────────────
    section("2. Screening universe")
    screened_ids = screen(price_df, SCREENER_CONFIG)
    print(f"  {len(UNIVERSE)} → {len(screened_ids)} stocks after screening")
    print(f"  Passed: {', '.join(screened_ids)}")

    if not screened_ids:
        print("  All stocks filtered out — aborting.")
        return

    price_df  = price_df[price_df["stock_id"].isin(screened_ids)]
    margin_df = margin_df[margin_df["stock_id"].isin(screened_ids)] if not margin_df.empty else margin_df
    fund_df   = fund_df[fund_df["stock_id"].isin(screened_ids)]     if not fund_df.empty  else fund_df

    # ── 3. Combined strategy (run once, no score filter yet) ──────────────────
    section("3. Running CombinedStrategy  (min_final_score=0 — all signals retained)")
    strategy = CombinedStrategy(COMBINED_CONFIG)
    full_result = strategy.generate(
        price_df        = price_df,
        margin_df       = margin_df if not margin_df.empty else None,
        fundamentals_df = fund_df   if not fund_df.empty  else None,
    )

    summary = strategy.summary(full_result)
    print(f"  Total signals : {summary['total_signals']}")
    print(f"  Score range   : {summary['score_mean']} avg,  {summary['score_max']} max")
    if summary["date_range"]:
        print(f"  Date range    : {summary['date_range'][0]}  →  {summary['date_range'][1]}")

    if full_result.empty:
        print("\n  No combined signals produced — aborting.")
        return

    # ── 4. Single-run with default parameters ─────────────────────────────────
    section(f"4. Single-run backtest  (hold={DEFAULT_HOLDING_DAYS}  top_n={DEFAULT_TOP_N}  min_score={DEFAULT_MIN_SCORE})")
    default_result = full_result[full_result["final_score"] >= DEFAULT_MIN_SCORE]
    ranked = rank_signals(default_result, top_n=DEFAULT_TOP_N)

    print(f"  Selection rows : {len(ranked)}")
    print(f"  Unique dates   : {ranked['date'].nunique()}")
    print(f"  Unique stocks  : {ranked['stock_id'].nunique()}")
    print("  Sample selections (latest 5 dates):")
    print_selected_stocks(ranked, last_n_dates=5)

    default_cfg = PortfolioConfig(
        holding_days    = DEFAULT_HOLDING_DAYS,
        top_n           = DEFAULT_TOP_N,
        min_score       = DEFAULT_MIN_SCORE,
        buy_on_next_day = True,
    )
    trades, metrics = run_portfolio_backtest(price_df, ranked, default_cfg)

    section("5. Default-run metrics")
    print_backtest_summary(metrics)

    if not trades.empty:
        section("6. Sample trades (first 10)")
        print_trade_sample(trades)

        section("7. Per-stock summary")
        print_per_stock_summary(trades)

    # ── 5. Parameter sweep ────────────────────────────────────────────────────
    section(
        f"8. Parameter sweep\n"
        f"   holding_days : {SWEEP_HOLDING_DAYS}\n"
        f"   top_n        : {SWEEP_TOP_N}\n"
        f"   min_score    : {SWEEP_MIN_SCORE}"
    )
    sweep_df = run_sweep(full_result, price_df)

    section("9. Sweep results  (sorted by cumulative return ↓)")
    print_sweep_table(sweep_df)

    # Best and worst
    best  = sweep_df.iloc[0]
    worst = sweep_df.iloc[-1]
    print(
        f"  Best : hold={int(best['holding_days'])}  top_n={int(best['top_n'])}"
        f"  min_score={best['min_score']:.1f}"
        f"  →  cum_ret={best['cum_return_%']:+.2f}%"
        f"  win={best['win_rate_%']:.1f}%  dd={best['max_dd_%']:.2f}%"
    )
    print(
        f"  Worst: hold={int(worst['holding_days'])}  top_n={int(worst['top_n'])}"
        f"  min_score={worst['min_score']:.1f}"
        f"  →  cum_ret={worst['cum_return_%']:+.2f}%"
        f"  win={worst['win_rate_%']:.1f}%  dd={worst['max_dd_%']:.2f}%"
    )
    print()

    section("Done")


if __name__ == "__main__":
    main()
