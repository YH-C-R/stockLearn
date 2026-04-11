"""Step 1: Generate historical recommendation events.

For each stock in a universe, run the full analysis pipeline and record
a recommendation row for every signal date produced by the scoring layer.
Output is a DataFrame of recommendation events — no forward returns yet.

Usage
-----
    python3 scripts/validate_recommendations.py
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from analysis.recommendation import Recommendation, RecommendationResult, recommend
from analysis.single_stock_analysis import analyze_stock
from analysis.single_stock_scoring import ScoreSnapshot, StockScoreResult, score_stock
from config.credentials import FINMIND_TOKEN
from data.single_stock_loader import StockData, load_stock

# ---------------------------------------------------------------------------
# Universe & date range — edit to experiment
# ---------------------------------------------------------------------------

UNIVERSE = [
    "2330",   # TSMC
    "2317",   # Foxconn
    "2454",   # MediaTek
    "2412",   # Chunghwa Telecom
    "2882",   # Cathay Financial
]

START_DATE = date(2023, 1, 1)
END_DATE   = date(2023, 12, 31)

# EPS lookback needed by the loader to avoid NaN at the start of the window
FUND_START = date(2021, 1, 1)


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def generate_recommendation_events(
    universe:   list[str],
    start_date: date,
    end_date:   date,
    token:      str | None = None,
) -> pd.DataFrame:
    """Run the full pipeline for each stock and return all recommendation events.

    For each stock, the pipeline runs once (one API fetch).  The scoring
    layer produces a ``history`` DataFrame — one row per signal date.
    For every row in that history, this function:
      1. Builds a point-in-time snapshot (scores as of that date).
      2. Filters ``data.daily`` to data available on or before that date.
      3. Calls ``recommend()`` to get the label, reasons, and entry price.

    Parameters
    ----------
    universe   : List of stock tickers to process.
    start_date : Start of the analysis window.
    end_date   : End of the analysis window.
    token      : FinMind API token.

    Returns
    -------
    DataFrame with columns:
        stock_id, date, recommendation, final_score,
        pv_score, mt_score, dd_score,
        current_price, suggested_entry, reasons
    Sorted by (date, stock_id).  Empty if no signals were found.
    """
    all_rows: list[dict] = []

    for stock_id in universe:
        print(f"  Processing {stock_id} …", end=" ", flush=True)

        # ── 1. Load all data for the stock ────────────────────────────────────
        data = load_stock(stock_id, start_date, end_date, token=token)
        if data.daily.empty:
            print("no price data — skipped")
            continue

        # ── 2. Run strategies and scoring (once, full range) ──────────────────
        analysis = analyze_stock(data)
        scored   = score_stock(analysis)

        if scored.history.empty:
            print("0 signal dates")
            continue

        print(f"{len(scored.history)} signal date(s)")

        # ── 3. Generate a recommendation for each signal date ─────────────────
        for row in scored.history.itertuples(index=False):
            signal_date = row.date

            # Point-in-time snapshot for this date
            snap = ScoreSnapshot(
                date        = signal_date,
                pv_score    = float(row.pv_score),
                mt_score    = float(row.mt_score),
                dd_score    = float(row.dd_score),
                final_score = float(row.final_score),
            )

            # Filter daily data to only what was known on signal_date
            daily_at_date = data.daily[data.daily["date"] <= signal_date].copy()
            data_at_date  = StockData(
                stock_id   = data.stock_id,
                start_date = data.start_date,
                end_date   = signal_date,
                daily      = daily_at_date,
            )

            scored_at_date = StockScoreResult(
                stock_id = stock_id,
                snapshot = snap,
                history  = pd.DataFrame(),   # not needed for recommend()
            )

            rec = recommend(scored_at_date, data_at_date)
            all_rows.append(_rec_to_row(rec))

    if not all_rows:
        return _empty_events()

    return (
        pd.DataFrame(all_rows)
        .sort_values(["date", "stock_id"])
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rec_to_row(rec: RecommendationResult) -> dict:
    return {
        "stock_id":       rec.stock_id,
        "date":           rec.as_of_date,
        "recommendation": rec.recommendation.value,
        "final_score":    rec.final_score,
        "pv_score":       rec.pv_score,
        "mt_score":       rec.mt_score,
        "dd_score":       rec.dd_score,
        "current_price":  rec.current_price,
        "suggested_entry": rec.suggested_entry,
        "reasons":        "; ".join(rec.reasons),
    }


def _empty_events() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "stock_id", "date", "recommendation", "final_score",
        "pv_score", "mt_score", "dd_score",
        "current_price", "suggested_entry", "reasons",
    ])


def _print_summary(events: pd.DataFrame) -> None:
    """Print a human-readable summary of the events DataFrame."""
    div = "─" * 60

    print(f"\n{div}")
    print(f"  Recommendation events: {len(events)} rows")
    print(div)

    if events.empty:
        print("  (none)\n")
        return

    print(f"  Date range  : {events['date'].min()}  →  {events['date'].max()}")
    print(f"  Stocks      : {events['stock_id'].nunique()}")

    print(f"\n  Distribution:")
    counts = events["recommendation"].value_counts()
    for label in ["STRONG BUY", "WATCH", "WAIT", "AVOID"]:
        n = counts.get(label, 0)
        bar = "█" * n
        print(f"    {label:<12}: {n:>3}  {bar}")

    print(f"\n  Sample events (first 10):\n")
    cols = ["date", "stock_id", "recommendation", "final_score", "current_price", "suggested_entry"]
    print(events[cols].head(10).to_string(index=False))
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    token = FINMIND_TOKEN or None

    print(f"\n  Generating recommendation events")
    print(f"  Universe   : {', '.join(UNIVERSE)}")
    print(f"  Date range : {START_DATE}  →  {END_DATE}\n")

    events = generate_recommendation_events(UNIVERSE, START_DATE, END_DATE, token=token)

    _print_summary(events)

    # Save to CSV for use in Step 2 (forward return calculation)
    out_path = Path(__file__).resolve().parents[1] / "outputs" / "recommendation_events.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(out_path, index=False)
    print(f"  Saved → {out_path}\n")


if __name__ == "__main__":
    main()
