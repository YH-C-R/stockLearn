"""Step 3: Summarize predictive value of recommendation labels.

Reads the enriched events produced by Step 2
(outputs/recommendation_events_with_returns.csv) and prints a performance
summary grouped by recommendation label.

Usage
-----
    python3 scripts/summarize_recommendation_performance.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LABEL_ORDER = ["STRONG BUY", "WATCH", "WAIT", "AVOID"]
HORIZONS    = [20, 60, 120]

INPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "outputs"
    / "recommendation_events_with_returns.csv"
)


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def summarize_performance(events: pd.DataFrame) -> pd.DataFrame:
    """Return a summary DataFrame grouped by recommendation label.

    Parameters
    ----------
    events : DataFrame with columns recommendation, return_20d,
             return_60d, return_120d.

    Returns
    -------
    DataFrame indexed by recommendation label with columns:
        n_events,
        avg_20d, avg_60d, avg_120d,
        winrate_20d, winrate_60d, winrate_120d
    Rows are ordered by LABEL_ORDER; labels with no events are omitted.
    """
    rows = []

    for label in LABEL_ORDER:
        subset = events[events["recommendation"] == label]
        if subset.empty:
            continue

        row: dict = {"recommendation": label, "n_events": len(subset)}

        for h in HORIZONS:
            col    = f"return_{h}d"
            series = subset[col].dropna()
            n      = len(series)

            row[f"avg_{h}d"]    = round(series.mean(), 2) if n > 0 else float("nan")
            row[f"winrate_{h}d"] = round((series > 0).sum() / n * 100, 1) if n > 0 else float("nan")

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).set_index("recommendation")


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def print_summary(summary: pd.DataFrame) -> None:
    """Print the summary table in a fixed-width format."""
    div = "─" * 78

    print(f"\n{div}")
    print("  Recommendation Performance Summary")
    print(div)

    if summary.empty:
        print("  (no data)\n")
        return

    # Header
    print(
        f"  {'Label':<12}  {'N':>5}  "
        f"{'Avg20d':>7}  {'Avg60d':>7}  {'Avg120d':>8}  "
        f"{'WR20d':>6}  {'WR60d':>6}  {'WR120d':>7}"
    )
    print(f"  {'─'*12}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*8}  {'─'*6}  {'─'*6}  {'─'*7}")

    def _fmt_pct(val, suffix=""):
        return "N/A" if pd.isna(val) else f"{val:+.2f}{suffix}"

    def _fmt_wr(val):
        return "N/A" if pd.isna(val) else f"{val:.1f}%"

    for label, row in summary.iterrows():
        print(
            f"  {label:<12}  {int(row['n_events']):>5}  "
            f"  {_fmt_pct(row['avg_20d'], '%'):>7}  "
            f"  {_fmt_pct(row['avg_60d'], '%'):>7}  "
            f"  {_fmt_pct(row['avg_120d'], '%'):>8}  "
            f"  {_fmt_wr(row['winrate_20d']):>6}  "
            f"  {_fmt_wr(row['winrate_60d']):>6}  "
            f"  {_fmt_wr(row['winrate_120d']):>7}"
        )

    print(div)
    print("  Avg = average return (%)   WR = win rate (% of events with positive return)\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not INPUT_PATH.exists():
        print(f"\n  ERROR: {INPUT_PATH} not found.")
        print("  Run scripts/calculate_forward_returns.py first.\n")
        sys.exit(1)

    events = pd.read_csv(INPUT_PATH)
    print(f"\n  Loaded {len(events)} event(s)  |  stocks: {sorted(events['stock_id'].astype(str).unique())}")

    # Coverage check
    print()
    for h in HORIZONS:
        col     = f"return_{h}d"
        n_valid = events[col].notna().sum()
        print(f"  return_{h:>3}d coverage: {n_valid} / {len(events)}")

    summary = summarize_performance(events)
    print_summary(summary)


if __name__ == "__main__":
    main()
