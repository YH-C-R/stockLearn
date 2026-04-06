"""Demo: Davis Double strategy → backtest."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from backtesting.engine import BacktestConfig, run_simple_backtest
from config.credentials import FINMIND_TOKEN
from data.fetchers.fundamentals import fetch_eps_data
from data.fetchers.price import fetch_daily_price
from strategies.davis_double import DavisDoubleStrategy

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STOCK_ID   = "2330"
START_DATE = date(2024, 1, 1)
END_DATE   = date(2024, 12, 31)
FUND_START = date(2022, 1, 1)   # needs ~5 quarters of history for YoY

BACKTEST_CONFIG = BacktestConfig(
    holding_days=20,    # quarterly signal → hold ~1 month
    min_score=0.5,
    buy_on_next_day=True,
)

STRATEGY = DavisDoubleStrategy(
    ma_window=60,
    yoy_threshold=0.30,   # 30% YoY EPS growth required
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'─' * 55}\n  {title}\n{'─' * 55}")


def signals_to_df(signals: list) -> pd.DataFrame:
    return pd.DataFrame([
        {"date": s.date, "score": s.score, "signal_name": s.signal_name}
        for s in signals
    ])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    token = FINMIND_TOKEN or None

    # 1. Fetch ----------------------------------------------------------------
    section(f"1. Fetching  {STOCK_ID}  {START_DATE} → {END_DATE}")
    price_df = fetch_daily_price(STOCK_ID, START_DATE, END_DATE, token=token)
    fund_df  = fetch_eps_data(STOCK_ID, FUND_START, END_DATE, token=token)
    print(f"  Price rows       : {len(price_df)}")
    print(f"  Quarters fetched : {len(fund_df)}")

    # 2. Generate signals -----------------------------------------------------
    section("2. Running DavisDoubleStrategy")
    print(
        f"  ma_window={STRATEGY.ma_window}  "
        f"yoy_threshold={STRATEGY.yoy_threshold:.0%}"
    )
    signals = STRATEGY.generate(price_df, fundamentals_df=fund_df)
    print(f"  {len(signals)} signal(s) generated")

    if signals:
        scores = [s.score for s in signals]
        print(f"  Score range : {min(scores):+.2f} – {max(scores):+.2f}")

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
