"""Demo: Phase 3 multi-stock portfolio backtest.

Pipeline
--------
  1. Fetch price, margin, and fundamentals for a small universe.
  2. Screen stocks by minimum volume / price.
  3. Run CombinedStrategy → aggregate → rank top-N per date.
  4. Feed ranked selections into PortfolioBacktest.
  5. Print portfolio metrics and trade samples.

Run
---
    python3 scripts/demo_phase3_backtest.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from backtesting.portfolio import PortfolioConfig, run_portfolio_backtest
from config.credentials import FINMIND_TOKEN
from data.fetchers.fundamentals import fetch_eps_data
from data.fetchers.margin import fetch_margin_data
from data.fetchers.price import fetch_daily_price
from strategies.combined import CombinedStrategy, CombinedStrategyConfig, rank_signals
from universe.screener import ScreenerConfig, screen

# ---------------------------------------------------------------------------
# Parameters — edit these to experiment
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

START_DATE = date(2024, 1, 1)
END_DATE   = date(2024, 12, 31)
FUND_START = date(2022, 1, 1)   # needs ~5 quarters for YoY

TOP_N      = 3   # stocks selected per signal date

PORTFOLIO_CONFIG = PortfolioConfig(
    holding_days    = 10,
    top_n           = TOP_N,
    min_score       = 0.3,
    buy_on_next_day = True,
)

COMBINED_CONFIG = CombinedStrategyConfig(
    mt_cooldown_days    = 10,
    dd_persistence_days = 5,
    min_final_score     = 0.3,
)

SCREENER_CONFIG = ScreenerConfig(
    min_avg_volume = 500_000,
    min_price      = 10.0,
    volume_window  = 20,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")


def fetch_all(stock_ids: list[str], token: str | None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fetch price, margin, and fundamentals for all stocks."""
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    token = FINMIND_TOKEN or None

    # ── 1. Fetch ─────────────────────────────────────────────────────────────
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

    # ── 3. Combined strategy ──────────────────────────────────────────────────
    section("3. Running CombinedStrategy")
    strategy = CombinedStrategy(COMBINED_CONFIG)
    result = strategy.generate(
        price_df       = price_df,
        margin_df      = margin_df if not margin_df.empty else None,
        fundamentals_df= fund_df   if not fund_df.empty  else None,
    )

    summary = strategy.summary(result)
    print(f"  Combined signals  : {summary['total_signals']}")
    print(f"  Score range       : {summary['score_mean']} avg,  {summary['score_max']} max")
    if summary["date_range"]:
        print(f"  Date range        : {summary['date_range'][0]}  →  {summary['date_range'][1]}")

    if result.empty:
        print("\n  No combined signals produced — aborting.")
        return

    # ── 4. Rank and select top-N ──────────────────────────────────────────────
    section(f"4. Ranking — top {TOP_N} stocks per date")
    ranked = rank_signals(result, top_n=TOP_N)
    print(f"  Selection rows    : {len(ranked)}")
    print(f"  Unique dates      : {ranked['date'].nunique()}")
    print(f"  Unique stocks     : {ranked['stock_id'].nunique()}")

    # Sample: latest 5 signal dates
    latest_dates = sorted(ranked["date"].unique())[-5:]
    sample = ranked[ranked["date"].isin(latest_dates)]
    print(f"\n  Sample selections (latest {len(latest_dates)} dates):\n")
    print(f"  {'date':<12}  {'rank':>4}  {'stock_id':>10}  {'final_score':>12}")
    print("  " + "─" * 44)
    prev = None
    for row in sample.itertuples(index=False):
        if prev and row.date != prev:
            print()
        print(f"  {str(row.date):<12}  {row.rank:>4}  {row.stock_id:>10}  {row.final_score:>12.4f}")
        prev = row.date

    # ── 5. Portfolio backtest ─────────────────────────────────────────────────
    section("5. Portfolio backtest")
    print(
        f"  holding_days={PORTFOLIO_CONFIG.holding_days}  "
        f"top_n={PORTFOLIO_CONFIG.top_n}  "
        f"min_score={PORTFOLIO_CONFIG.min_score}  "
        f"buy_on_next_day={PORTFOLIO_CONFIG.buy_on_next_day}"
    )

    trades, metrics = run_portfolio_backtest(price_df, ranked, PORTFOLIO_CONFIG)

    # ── 6. Metrics ────────────────────────────────────────────────────────────
    section("6. Portfolio metrics")
    print(f"  Trades            : {metrics['num_trades']}")
    print(f"  Trading days      : {metrics['num_trading_days']}")
    print(f"  Win rate          : {metrics['win_rate_pct']:.1f}%")
    print(f"  Avg return / trade: {metrics['avg_return_pct']:+.2f}%")
    print(f"  Cumulative return : {metrics['cumulative_return_pct']:+.2f}%")
    print(f"  Max drawdown      : {metrics['max_drawdown_pct']:.2f}%")

    # ── 7. Sample trades ──────────────────────────────────────────────────────
    if not trades.empty:
        section("7. Sample trades (first 10)")
        cols = ["signal_date", "stock_id", "entry_date", "exit_date",
                "entry_price", "exit_price", "return_pct", "score"]
        print(trades[cols].head(10).to_string(index=False))

        # Per-stock summary
        section("8. Per-stock summary")
        per_stock = (
            trades.groupby("stock_id")["return_pct"]
            .agg(trades="count", avg_return="mean", win_rate=lambda x: (x > 0).mean() * 100)
            .round(2)
            .sort_values("avg_return", ascending=False)
            .reset_index()
        )
        print(per_stock.to_string(index=False))

    section("Done")


if __name__ == "__main__":
    main()
