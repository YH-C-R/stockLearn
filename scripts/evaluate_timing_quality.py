"""Step 3b: Evaluate timing quality of recommendation labels.

Reads the enriched events (outputs/recommendation_events_with_returns.csv)
and summarises short-term return and max drawdown per recommendation tier.

Goal: check whether STRONG BUY has smaller drawdowns and AVOID has worse
short-term returns — i.e., whether the label captures entry timing quality.

Usage
-----
    python3 scripts/evaluate_timing_quality.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LABEL_ORDER = ["STRONG BUY", "WATCH", "WAIT", "AVOID"]

INPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "outputs"
    / "recommendation_events_with_returns.csv"
)


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def summarize_timing(events: pd.DataFrame) -> pd.DataFrame:
    """Return a timing-quality summary grouped by recommendation label.

    Parameters
    ----------
    events : DataFrame with columns recommendation, return_5d, return_10d,
             max_drawdown_20d.

    Returns
    -------
    DataFrame indexed by recommendation label with columns:
        n_events, avg_5d, avg_10d, avg_drawdown_20d
    Rows ordered by LABEL_ORDER; labels with no events are omitted.
    """
    rows = []

    for label in LABEL_ORDER:
        subset = events[events["recommendation"] == label]
        if subset.empty:
            continue

        def _avg(col: str) -> float:
            s = subset[col].dropna()
            return round(s.mean(), 2) if not s.empty else float("nan")

        rows.append({
            "recommendation":   label,
            "n_events":         len(subset),
            "avg_5d":           _avg("return_5d"),
            "avg_10d":          _avg("return_10d"),
            "avg_drawdown_20d": _avg("max_drawdown_20d"),
        })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).set_index("recommendation")


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def print_timing_summary(summary: pd.DataFrame) -> None:
    div = "─" * 62

    print(f"\n{div}")
    print("  Timing Quality — Short-Term Return & Drawdown")
    print(div)

    if summary.empty:
        print("  (no data)\n")
        return

    print(
        f"  {'Label':<12}  {'N':>5}  "
        f"{'Avg 5d':>8}  {'Avg 10d':>8}  {'Avg DD-20d':>11}"
    )
    print(f"  {'─'*12}  {'─'*5}  {'─'*8}  {'─'*8}  {'─'*11}")

    def _fmt(val: float, suffix: str = "%") -> str:
        return "N/A" if pd.isna(val) else f"{val:+.2f}{suffix}"

    for label, row in summary.iterrows():
        print(
            f"  {label:<12}  {int(row['n_events']):>5}  "
            f"  {_fmt(row['avg_5d']):>8}  "
            f"  {_fmt(row['avg_10d']):>8}  "
            f"  {_fmt(row['avg_drawdown_20d']):>11}"
        )

    print(div)
    print("  Avg 5d / 10d = avg return after 5 / 10 trading days")
    print("  Avg DD-20d   = avg worst drop within next 20 trading days\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not INPUT_PATH.exists():
        print(f"\n  ERROR: {INPUT_PATH} not found.")
        print("  Run scripts/calculate_forward_returns.py first.\n")
        sys.exit(1)

    events = pd.read_csv(INPUT_PATH)

    # Check that timing columns are present (script may need to be re-run)
    missing = [c for c in ("return_5d", "return_10d", "max_drawdown_20d")
               if c not in events.columns]
    if missing:
        print(f"\n  ERROR: missing columns: {missing}")
        print("  Re-run scripts/calculate_forward_returns.py to regenerate.\n")
        sys.exit(1)

    print(f"\n  Loaded {len(events)} event(s)  |  "
          f"stocks: {sorted(events['stock_id'].astype(str).unique())}")

    summary = summarize_timing(events)
    print_timing_summary(summary)


if __name__ == "__main__":
    main()
