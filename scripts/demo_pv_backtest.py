"""Demo: price-volume strategy → backtest."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from backtesting.engine import BacktestConfig, run_simple_backtest
from backtesting.report import print_backtest_summary, print_trade_sample
from config.credentials import FINMIND_TOKEN
from data.fetchers.price import fetch_daily_price
from strategies.price_volume import PriceVolumeStrategy

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STOCK_ID   = "2330"
START_DATE = date(2024, 1, 1)
END_DATE   = date(2024, 12, 31)

BACKTEST_CONFIG = BacktestConfig(
    holding_days=5,
    min_score=0.8,
    buy_on_next_day=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'─' * 55}\n  {title}\n{'─' * 55}")


def signals_to_df(signals: list) -> pd.DataFrame:
    """Convert a list of Signal objects to a DataFrame for the backtest engine."""
    return pd.DataFrame([
        {"date": s.date, "score": s.score, "signal_name": s.signal_name}
        for s in signals
    ])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # 1. Fetch ----------------------------------------------------------------
    section(f"1. Fetching  {STOCK_ID}  {START_DATE} → {END_DATE}")
    df = fetch_daily_price(
        stock_id=STOCK_ID,
        start_date=START_DATE,
        end_date=END_DATE,
        token=FINMIND_TOKEN or None,
    )
    print(f"  {len(df)} rows fetched.")

    # 2. Generate signals -----------------------------------------------------
    section("2. Running PriceVolumeStrategy")
    strategy = PriceVolumeStrategy()
    print(
        f"  price_window={strategy.price_window}  "
        f"volume_window={strategy.volume_window}  "
        f"volume_surge_mult={strategy.volume_surge_mult}×"
    )
    signals = strategy.generate(df)
    print(f"  {len(signals)} signal(s) generated  "
          f"(min_score filter: {BACKTEST_CONFIG.min_score})")

    # 3. Run backtest ---------------------------------------------------------
    section("3. Running backtest")
    print(f"  holding_days={BACKTEST_CONFIG.holding_days}  "
          f"buy_on_next_day={BACKTEST_CONFIG.buy_on_next_day}")

    trades, metrics = run_simple_backtest(df, signals_to_df(signals), BACKTEST_CONFIG)

    # 4. Metrics --------------------------------------------------------------
    section("4. Results")
    print_backtest_summary(metrics)

    # 5. Sample trades --------------------------------------------------------
    if not trades.empty:
        section("5. Sample trades (up to 10)")
        print_trade_sample(trades)

    section("Done")


if __name__ == "__main__":
    main()
