"""Run a simple backtest for a single stock and print results.

Usage
-----
    python3 scripts/run_backtest.py                        # defaults
    python3 scripts/run_backtest.py 2454                   # custom ticker
    python3 scripts/run_backtest.py 2454 2023-01-01 2025-12-31
"""

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.backtest_service import NoDataError, run_backtest_flow
from config.credentials import FINMIND_TOKEN

DEFAULT_STOCK_ID = "2330"
DEFAULT_START    = date(2023, 1, 1)
DEFAULT_END      = date(2025, 12, 31)


def parse_args() -> tuple[str, date, date]:
    args = sys.argv[1:]
    stock_id   = args[0] if len(args) > 0 else DEFAULT_STOCK_ID
    start_date = _parse_date(args[1]) if len(args) > 1 else DEFAULT_START
    end_date   = _parse_date(args[2]) if len(args) > 2 else DEFAULT_END
    return stock_id, start_date, end_date


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    stock_id, start_date, end_date = parse_args()
    div = "─" * 52

    print(f"\n{div}")
    print(f"  Backtest  |  {stock_id}  |  {start_date}  →  {end_date}")
    print(div)

    # ── Load data + run backtest ──────────────────────────────────────────────
    print("  Loading data...")
    try:
        result = run_backtest_flow(
            stock_id, start_date, end_date, token=FINMIND_TOKEN or None
        )
    except NoDataError:
        print(f"  No data for {stock_id}. Aborting.")
        sys.exit(1)

    print(f"  Data loaded: {result.loaded_start} → {result.loaded_end}")
    print("  Running backtest (this may take a moment)...\n")

    trades  = result.trades
    metrics = result.metrics

    print(f"{div}")
    print(f"  Metrics")
    print(div)
    print(f"  {'Number of trades':<20}: {metrics['number_of_trades']}")
    print(f"  {'Win rate':<20}: {metrics['win_rate']:.2%}")
    print(f"  {'Average return':<20}: {metrics['average_return']:.2%}")
    print(f"  {'Total return':<20}: {metrics['total_return']:.2%}")
    print(f"  {'Max drawdown':<20}: {metrics['max_drawdown']:.2%}")

    # ── First 5 trades ────────────────────────────────────────────────────────
    print(f"\n{div}")
    print(f"  First {min(5, len(trades))} trades")
    print(div)

    if not trades:
        print("  No completed trades.")
    else:
        print(f"  {'Entry date':<14}  {'Exit date':<14}  {'Entry':>8}  {'Exit':>8}  {'Return':>8}")
        print(f"  {'─'*12:<14}  {'─'*12:<14}  {'─'*8:>8}  {'─'*8:>8}  {'─'*8:>8}")
        for t in trades[:5]:
            ret = f"{t['return']:.2%}" if t["return"] is not None else "—"
            print(
                f"  {str(t['entry_date']):<14}  {str(t['exit_date']):<14}"
                f"  {t['entry_price']:>8.2f}  {t['exit_price']:>8.2f}  {ret:>8}"
            )

    print(f"{div}\n")


if __name__ == "__main__":
    main()
