"""Demo: margin-trend strategy → backtest."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from backtesting.engine import BacktestConfig, run_simple_backtest
from config.credentials import FINMIND_TOKEN
from data.fetchers.margin import fetch_margin_data
from data.fetchers.price import fetch_daily_price
from strategies.margin_trend import MarginTrendStrategy

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STOCK_ID   = "2330"
START_DATE = date(2024, 1, 1)
END_DATE   = date(2024, 12, 31)

BACKTEST_CONFIG = BacktestConfig(
    holding_days=5,
    min_score=0.3,       # margin_trend scores are smaller — lower bar than price_volume
    buy_on_next_day=True,
)

STRATEGY = MarginTrendStrategy(
    window=5,
    surge_threshold=0.05,
    unwind_threshold=0.03,
    min_abs_score=0.3,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'─' * 55}\n  {title}\n{'─' * 55}")


def signals_to_df(signals: list) -> pd.DataFrame:
    return pd.DataFrame([
        {"date": s.date, "score": s.score, "direction": s.direction}
        for s in signals
    ])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    token = FINMIND_TOKEN or None

    # 1. Fetch ----------------------------------------------------------------
    section(f"1. Fetching  {STOCK_ID}  {START_DATE} → {END_DATE}")
    price_df  = fetch_daily_price(STOCK_ID, START_DATE, END_DATE, token=token)
    margin_df = fetch_margin_data(STOCK_ID, START_DATE, END_DATE, token=token)
    print(f"  Price rows  : {len(price_df)}")
    print(f"  Margin rows : {len(margin_df)}")

    # 2. Generate signals -----------------------------------------------------
    section("2. Running MarginTrendStrategy")
    print(
        f"  window={STRATEGY.window}  "
        f"surge_threshold={STRATEGY.surge_threshold}  "
        f"unwind_threshold={STRATEGY.unwind_threshold}  "
        f"min_abs_score={STRATEGY.min_abs_score}"
    )
    signals = STRATEGY.generate(price_df, margin_df=margin_df)
    print(f"  {len(signals)} signal(s) generated")

    if signals:
        sig_df = signals_to_df(signals)
        counts = sig_df["direction"].value_counts()
        for direction, count in counts.items():
            print(f"    {direction:<10} : {count}")

    # 3. Run backtest ---------------------------------------------------------
    section("3. Running backtest")
    print(
        f"  holding_days={BACKTEST_CONFIG.holding_days}  "
        f"min_score={BACKTEST_CONFIG.min_score}  "
        f"buy_on_next_day={BACKTEST_CONFIG.buy_on_next_day}"
    )

    trades, metrics = run_simple_backtest(
        price_df,
        signals_to_df(signals),
        BACKTEST_CONFIG,
    )

    # 4. Metrics --------------------------------------------------------------
    section("4. Results")
    print(f"  Trades            : {metrics['num_trades']}")
    print(f"  Win rate          : {metrics['win_rate_pct']:.1f}%")
    print(f"  Avg return        : {metrics['avg_return_pct']:+.2f}%")
    print(f"  Cumulative return : {metrics['cumulative_return_pct']:+.2f}%")
    print(f"  Max drawdown      : {metrics['max_drawdown_pct']:.2f}%")

    # 5. Sample trades --------------------------------------------------------
    if not trades.empty:
        section("5. Sample trades (up to 10)")
        print(trades.head(10).to_string(index=False))

    section("Done")


if __name__ == "__main__":
    main()
