"""Demo: Phase 3 full pipeline — screen → aggregate → rank.

Pipeline
--------
  1. Fetch price, margin, and fundamentals for a small stock universe.
  2. Screen stocks by minimum avg-volume and price.
  3. Run PriceVolumeStrategy, MarginTrendStrategy, DavisDoubleStrategy.
  4. Aggregate into a combined scored DataFrame.
  5. Rank stocks by final_score per date.
  6. Print top-N selections for the most recent dates.

Run
---
    python3 scripts/demo_phase3_combined.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from config.credentials import FINMIND_TOKEN
from data.fetchers.fundamentals import fetch_eps_data
from data.fetchers.margin import fetch_margin_data
from data.fetchers.price import fetch_daily_price
from strategies.combined import CombinedStrategy, CombinedStrategyConfig, rank_signals
from universe.screener import ScreenerConfig, screen, screen_df

# ---------------------------------------------------------------------------
# Universe & date range
# ---------------------------------------------------------------------------

# A small representative universe across sectors
UNIVERSE = [
    "2330",   # TSMC           (semiconductors)
    "2317",   # Foxconn         (electronics)
    "2454",   # MediaTek        (semiconductors)
    "2412",   # Chunghwa Telecom(telecom)
    "2882",   # Cathay Financial(financials)
    "2308",   # Delta Electronics(power components)
    "3711",   # ASMedia         (IC design)
    "2357",   # Asustek         (PC/notebooks)
]

START_DATE  = date(2024, 1, 1)
END_DATE    = date(2024, 12, 31)
FUND_START  = date(2022, 1, 1)   # needs ~5 quarters for YoY
TOP_N       = 3                  # stocks to select per day

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'═' * 60}\n  {title}\n{'═' * 60}")


def subsection(title: str) -> None:
    print(f"\n  ── {title}")


def banner() -> None:
    print(
        "\n"
        "╔══════════════════════════════════════════════════════════╗\n"
        "║         Phase 3 Demo — Combined Strategy Pipeline        ║\n"
        "╚══════════════════════════════════════════════════════════╝"
    )


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def fetch_universe_price(stock_ids: list[str], token: str | None) -> pd.DataFrame:
    frames = []
    for sid in stock_ids:
        try:
            df = fetch_daily_price(sid, START_DATE, END_DATE, token=token)
            frames.append(df)
            print(f"    {sid}: {len(df)} rows")
        except Exception as exc:
            print(f"    {sid}: FAILED — {exc}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_universe_margin(stock_ids: list[str], token: str | None) -> pd.DataFrame:
    frames = []
    for sid in stock_ids:
        try:
            df = fetch_margin_data(sid, START_DATE, END_DATE, token=token)
            frames.append(df)
            print(f"    {sid}: {len(df)} rows")
        except Exception as exc:
            print(f"    {sid}: FAILED — {exc}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_universe_fundamentals(stock_ids: list[str], token: str | None) -> pd.DataFrame:
    frames = []
    for sid in stock_ids:
        try:
            df = fetch_eps_data(sid, FUND_START, END_DATE, token=token)
            frames.append(df)
            print(f"    {sid}: {len(df)} quarters")
        except Exception as exc:
            print(f"    {sid}: FAILED — {exc}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    banner()
    token = FINMIND_TOKEN or None

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    section("1. Fetching data")

    subsection("Price data")
    price_df = fetch_universe_price(UNIVERSE, token)
    print(f"\n  Total price rows: {len(price_df)}")

    subsection("Margin data")
    margin_df = fetch_universe_margin(UNIVERSE, token)
    print(f"\n  Total margin rows: {len(margin_df)}")

    subsection("Fundamentals data")
    fund_df = fetch_universe_fundamentals(UNIVERSE, token)
    print(f"\n  Total fundamental quarters: {len(fund_df)}")

    if price_df.empty:
        print("\n  No price data fetched — aborting.")
        return

    # ── 2. Screen universe ───────────────────────────────────────────────────
    section("2. Screening universe")
    print(f"  Stocks before screening : {len(UNIVERSE)}")

    screener_cfg = ScreenerConfig(
        min_avg_volume=500_000,
        min_price=10.0,
        volume_window=20,
    )
    summary_df = screen_df(price_df, screener_cfg)
    screened_ids = summary_df["stock_id"].tolist()

    print(f"  Stocks after  screening : {len(screened_ids)}")
    print(f"\n  {'stock_id':>10}  {'avg_volume':>14}  {'last_close':>12}")
    print("  " + "─" * 42)
    for row in summary_df.itertuples(index=False):
        print(
            f"  {row.stock_id:>10}  {row.avg_volume:>14,.0f}"
            f"  {row.last_close:>12.2f}"
        )

    if not screened_ids:
        print("\n  All stocks filtered out — aborting.")
        return

    # Filter all DataFrames to screened universe
    price_df  = price_df[price_df["stock_id"].isin(screened_ids)]
    margin_df = margin_df[margin_df["stock_id"].isin(screened_ids)] if not margin_df.empty else margin_df
    fund_df   = fund_df[fund_df["stock_id"].isin(screened_ids)]     if not fund_df.empty  else fund_df

    # ── 3. Run combined strategy ─────────────────────────────────────────────
    section("3. Running CombinedStrategy")
    cfg = CombinedStrategyConfig(
        pv_price_window=20,
        pv_volume_window=20,
        pv_volume_surge_mult=2.0,
        pv_emit_weak_signals=True,
        mt_window=5,
        mt_min_abs_score=0.3,
        dd_ma_window=60,
        dd_yoy_threshold=0.30,
        min_final_score=0.0,
    )
    strategy = CombinedStrategy(cfg)

    result = strategy.generate(
        price_df=price_df,
        margin_df=margin_df if not margin_df.empty else None,
        fundamentals_df=fund_df if not fund_df.empty else None,
    )

    summary = strategy.summary(result)
    print(f"  total signals   : {summary['total_signals']}")
    if summary["date_range"]:
        print(f"  date range      : {summary['date_range'][0]}  →  {summary['date_range'][1]}")
    print(f"  avg final_score : {summary['score_mean']}")
    print(f"  max final_score : {summary['score_max']}")

    # Per-strategy signal counts
    if not result.empty:
        subsection("Signal counts per strategy")
        for col, label in [
            ("price_volume_score",  "price_volume "),
            ("margin_trend_score",  "margin_trend "),
            ("davis_double_score",  "davis_double "),
        ]:
            if col in result.columns:
                count = (result[col] > 0).sum()
                print(f"    {label} signals : {count}")

    # ── 4. Aggregated score sample ───────────────────────────────────────────
    section("4. Aggregated score sample (latest 15 rows)")
    if result.empty:
        print("  No aggregated results.")
    else:
        score_cols = [
            "stock_id", "date",
            "price_volume_score", "margin_trend_score",
            "davis_double_score", "final_score",
        ]
        sample = result.tail(15)[score_cols].copy()
        sample = sample.sort_values(["date", "final_score"], ascending=[True, False])

        print(f"\n  {'stock_id':>10}  {'date':<12}  {'pv_score':>9}  "
              f"{'mt_score':>9}  {'dd_score':>9}  {'final':>8}")
        print("  " + "─" * 68)
        for row in sample.itertuples(index=False):
            print(
                f"  {row.stock_id:>10}  {str(row.date):<12}"
                f"  {row.price_volume_score:>9.4f}"
                f"  {row.margin_trend_score:>9.4f}"
                f"  {row.davis_double_score:>9.4f}"
                f"  {row.final_score:>8.4f}"
            )

    # ── 5. Rank and top-N selection ──────────────────────────────────────────
    section(f"5. Top-{TOP_N} stocks per date (latest 5 signal dates)")
    if result.empty:
        print("  No signals to rank.")
    else:
        ranked = rank_signals(result, top_n=TOP_N)

        if ranked.empty:
            print("  No ranked results.")
        else:
            latest_dates = sorted(ranked["date"].unique())[-5:]
            top_recent   = ranked[ranked["date"].isin(latest_dates)]

            print(f"\n  {'date':<12}  {'rank':>4}  {'stock_id':>10}  {'final_score':>12}")
            print("  " + "─" * 44)

            prev_date = None
            for row in top_recent.itertuples(index=False):
                if prev_date and row.date != prev_date:
                    print()   # blank line between dates
                print(
                    f"  {str(row.date):<12}  {row.rank:>4}  "
                    f"{row.stock_id:>10}  {row.final_score:>12.4f}"
                )
                prev_date = row.date

    section("Done")


if __name__ == "__main__":
    main()
