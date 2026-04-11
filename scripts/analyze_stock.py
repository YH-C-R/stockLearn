"""Full single-stock analysis pipeline.

Loads data, runs all applicable strategies, computes a combined score,
and prints a recommendation report.

Usage
-----
    python3 scripts/analyze_stock.py                        # defaults
    python3 scripts/analyze_stock.py 2454                   # custom ticker
    python3 scripts/analyze_stock.py 2454 2023-01-01 2023-12-31
"""

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.recommendation import print_recommendation, recommend
from analysis.single_stock_analysis import analyze_stock
from analysis.single_stock_scoring import score_stock
from config.credentials import FINMIND_TOKEN
from data.single_stock_loader import load_stock

# ---------------------------------------------------------------------------
# Defaults — override via CLI args
# ---------------------------------------------------------------------------

DEFAULT_STOCK_ID  = "2330"
DEFAULT_START     = date(2023, 1, 1)
DEFAULT_END       = date(2023, 12, 31)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_args() -> tuple[str, date, date]:
    args = sys.argv[1:]
    stock_id   = args[0] if len(args) > 0 else DEFAULT_STOCK_ID
    start_date = _parse_date(args[1]) if len(args) > 1 else DEFAULT_START
    end_date   = _parse_date(args[2]) if len(args) > 2 else DEFAULT_END
    return stock_id, start_date, end_date


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def section(title: str) -> None:
    print(f"\n{'─' * 52}\n  {title}\n{'─' * 52}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    stock_id, start_date, end_date = parse_args()
    token = FINMIND_TOKEN or None

    print(f"\n  Stock Analysis Pipeline")
    print(f"  {stock_id}  |  {start_date}  →  {end_date}")

    # ── 1. Load data ──────────────────────────────────────────────────────────
    section("1. Loading data")
    data = load_stock(stock_id, start_date, end_date, token=token)

    if data.daily.empty:
        print(f"  No data available for {stock_id}. Aborting.")
        for w in data.warnings:
            print(f"  Warning: {w}")
        sys.exit(1)

    s = data.summary()
    print(f"  Rows           : {s['rows']}")
    print(f"  Date range     : {s['date_range'][0]}  →  {s['date_range'][1]}")
    print(f"  Price coverage : {s['price_coverage']}")
    print(f"  Margin coverage: {s['margin_coverage']}")
    print(f"  EPS coverage   : {s['eps_coverage']}")
    print(f"  PE coverage    : {s['pe_coverage']}")
    if data.warnings:
        for w in data.warnings:
            print(f"  Warning: {w}")

    # ── 2. Run strategies ─────────────────────────────────────────────────────
    section("2. Running strategies")
    analysis = analyze_stock(data)
    s = analysis.summary()
    print(f"  price_volume   : {s['price_volume']} signal(s)")
    print(f"  margin_trend   : {s['margin_trend']} signal(s)")
    print(f"  davis_double   : {s['davis_double']} signal(s)")
    print(f"  total          : {s['total']} signal(s)")
    if analysis.skipped:
        for strategy, reason in analysis.skipped.items():
            print(f"  Skipped [{strategy}]: {reason}")

    # ── 3. Compute score ──────────────────────────────────────────────────────
    section("3. Computing score")
    scored = score_stock(analysis)
    s = scored.summary()
    print(f"  Scored dates   : {s['scored_dates']}")
    if s["snapshot"]:
        snap = s["snapshot"]
        print(f"  Latest date    : {snap['date']}")
        print(f"  PV / MT / DD   : {snap['pv_score']:.4f} / {snap['mt_score']:.4f} / {snap['dd_score']:.4f}")
        print(f"  Final score    : {snap['final_score']:.4f}")
    else:
        print("  No scored dates — signals may not meet strategy conditions.")

    # ── 4. Recommendation ─────────────────────────────────────────────────────
    section("4. Recommendation")
    rec = recommend(scored, data)
    print_recommendation(rec)


if __name__ == "__main__":
    main()
