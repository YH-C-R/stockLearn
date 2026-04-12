"""Full single-stock analysis pipeline.

Purpose
-------
Show all signal information for one stock, including:
- raw strategy signals (price_volume / margin_trend / davis_double)
- old aggregated signal score
- long-term scorer
- short-term scorer
- final decision
- recommendation summary (UI layer only)

Usage
-----
    python3 scripts/analyze_stock.py
    python3 scripts/analyze_stock.py 2454
    python3 scripts/analyze_stock.py 2454 2023-01-01 2023-12-31
"""

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.decision_engine import make_decision, print_decision
from analysis.long_term_scorer import print_long_term_score, score_long_term
from analysis.recommendation import print_recommendation, recommend_from_decision
from analysis.short_term_scorer import print_short_term_score, score_short_term
from analysis.single_stock_analysis import analyze_stock
from analysis.single_stock_scoring import score_stock
from config.credentials import FINMIND_TOKEN
from data.single_stock_loader import load_stock


DEFAULT_STOCK_ID = "2330"
DEFAULT_START = date(2023, 1, 1)
DEFAULT_END = date(2023, 12, 31)


def parse_args() -> tuple[str, date, date]:
    args = sys.argv[1:]
    stock_id = args[0] if len(args) > 0 else DEFAULT_STOCK_ID
    start_date = _parse_date(args[1]) if len(args) > 1 else DEFAULT_START
    end_date = _parse_date(args[2]) if len(args) > 2 else DEFAULT_END
    return stock_id, start_date, end_date


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def section(title: str) -> None:
    print(f"\n{'─' * 52}\n  {title}\n{'─' * 52}")


def main() -> None:
    stock_id, start_date, end_date = parse_args()
    token = FINMIND_TOKEN or None

    print(f"\n  Stock Analysis Pipeline")
    print(f"  {stock_id}  |  {start_date}  →  {end_date}")

    # 1. Load data
    section("1. Loading data")
    data = load_stock(stock_id, start_date, end_date, token=token)

    if data.daily.empty:
        print(f"  No data available for {stock_id}. Aborting.")
        for w in data.warnings:
            print(f"  Warning: {w}")
        sys.exit(1)

    summary = data.summary()
    print(f"  Rows           : {summary['rows']}")
    print(f"  Date range     : {summary['date_range'][0]}  →  {summary['date_range'][1]}")
    print(f"  Price coverage : {summary['price_coverage']}")
    print(f"  Margin coverage: {summary['margin_coverage']}")
    print(f"  EPS coverage   : {summary['eps_coverage']}")
    print(f"  PE coverage    : {summary['pe_coverage']}")
    if data.warnings:
        for w in data.warnings:
            print(f"  Warning: {w}")

    # 2. Run legacy signal strategies (still useful for signal visibility)
    section("2. Running Signal Strategies")
    analysis = analyze_stock(data)
    analysis_summary = analysis.summary()
    print(f"  price_volume   : {analysis_summary['price_volume']} signal(s)")
    print(f"  margin_trend   : {analysis_summary['margin_trend']} signal(s)")
    print(f"  davis_double   : {analysis_summary['davis_double']} signal(s)")
    print(f"  total          : {analysis_summary['total']} signal(s)")
    if analysis.skipped:
        for strategy, reason in analysis.skipped.items():
            print(f"  Skipped [{strategy}]: {reason}")

    # 3. Old aggregated signal score (keep for reference only)
    section("3. Aggregated Signal Score (Reference)")
    scored = score_stock(analysis)
    scored_summary = scored.summary()
    print(f"  Scored dates   : {scored_summary['scored_dates']}")
    if scored_summary["snapshot"]:
        snap = scored_summary["snapshot"]
        print(f"  Latest date    : {snap['date']}")
        print(
            f"  PV / MT / DD   : "
            f"{snap['pv_score']:.4f} / {snap['mt_score']:.4f} / {snap['dd_score']:.4f}"
        )
        print(f"  Final score    : {snap['final_score']:.4f}")
    else:
        print("  No scored dates — signals may not meet strategy conditions.")

    # Compute new-system results once
    lt = score_long_term(data)
    st = score_short_term(data)
    dec = make_decision(lt, st)
    rec = recommend_from_decision(dec)

    # 4. Long-term
    section("4. Long-Term Fundamental Score")
    print_long_term_score(lt)

    # 5. Short-term
    section("5. Short-Term Timing Score")
    print_short_term_score(st)

    # 6. Final decision
    section("6. Final Decision")
    print_decision(dec)

    # 7. Recommendation summary (UI layer only)
    section("7. Recommendation Summary")
    print_recommendation(rec)


if __name__ == "__main__":
    main()