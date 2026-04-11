"""Step 2: Calculate forward returns for historical recommendation events.

Reads the recommendation events produced by Step 1
(outputs/recommendation_events.csv), fetches price data for each stock,
and attaches forward-return and drawdown columns.

Columns added
-------------
    return_5d, return_10d, return_20d, return_60d, return_120d
    max_drawdown_20d  — worst close-to-entry drop within next 20 trading days

Usage
-----
    python3 scripts/calculate_forward_returns.py
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from config.credentials import FINMIND_TOKEN
from data.fetchers.price import fetch_daily_price

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HORIZONS = [5, 10, 20, 60, 120]   # trading-day horizons
DRAWDOWN_WINDOW = 20              # trading days used for max_drawdown_20d
PRICE_BUFFER_DAYS = 200           # calendar days beyond the last event date
                                   # to ensure 120 trading days exist

EVENTS_PATH  = Path(__file__).resolve().parents[1] / "outputs" / "recommendation_events.csv"
OUTPUT_PATH  = Path(__file__).resolve().parents[1] / "outputs" / "recommendation_events_with_returns.csv"


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def add_forward_returns(
    events: pd.DataFrame,
    token:  str | None = None,
) -> pd.DataFrame:
    """Attach forward-return columns to a recommendation-events DataFrame.

    For each event row the function looks up the closing price N trading days
    after the signal date and computes the percentage return relative to
    ``current_price`` recorded in the event.

    Parameters
    ----------
    events : DataFrame produced by ``generate_recommendation_events()``.
             Must contain columns: stock_id, date, current_price.
    token  : FinMind API token.

    Returns
    -------
    Copy of *events* with new columns appended:
        return_5d, return_10d, return_20d, return_60d, return_120d,
        max_drawdown_20d
    Return values are percentage floats (e.g. 5.23 means +5.23 %).
    max_drawdown_20d is a negative or zero percentage (e.g. -3.5 means
    the worst close within 20 trading days was 3.5 % below entry).
    NaN where future price data is unavailable.
    """
    if events.empty:
        for h in HORIZONS:
            events[f"return_{h}d"] = pd.NA
        events["max_drawdown_20d"] = pd.NA
        return events

    events = events.copy()
    events["date"] = pd.to_datetime(events["date"]).dt.date

    # Pre-allocate output columns
    for h in HORIZONS:
        events[f"return_{h}d"] = float("nan")
    events["max_drawdown_20d"] = float("nan")

    # Determine per-stock fetch range: from earliest event to last event + buffer
    last_event_date = events["date"].max()
    price_end = last_event_date + timedelta(days=PRICE_BUFFER_DAYS)

    for stock_id, group in events.groupby("stock_id"):
        first_event = group["date"].min()
        print(f"  Fetching prices for {stock_id} …", end=" ", flush=True)

        try:
            price_df = fetch_daily_price(
                stock_id   = stock_id,
                start_date = first_event,
                end_date   = price_end,
                token      = token,
            )
        except Exception as exc:
            print(f"error ({exc}) — forward returns will be NaN")
            continue

        if price_df.empty:
            print("no price data")
            continue

        # Build a sorted Series: trading date → close price
        price_df["date"] = pd.to_datetime(price_df["date"]).dt.date
        price_df = price_df.sort_values("date").drop_duplicates("date")
        trading_dates = price_df["date"].tolist()
        close_by_date = price_df.set_index("date")["close"]

        print(f"{len(trading_dates)} trading day(s)")

        # For each event in this stock, look up forward prices
        for idx in group.index:
            signal_date   = events.at[idx, "date"]
            entry_price   = events.at[idx, "current_price"]

            if pd.isna(entry_price) or entry_price <= 0:
                continue

            # Find the position of signal_date (or the next available date)
            pos = _find_position(trading_dates, signal_date)
            if pos is None:
                continue

            # Forward returns at each horizon
            for h in HORIZONS:
                target_pos = pos + h
                if target_pos < len(trading_dates):
                    future_price = float(close_by_date[trading_dates[target_pos]])
                    ret = (future_price - entry_price) / entry_price * 100.0
                    events.at[idx, f"return_{h}d"] = round(ret, 4)

            # Max drawdown within the next DRAWDOWN_WINDOW trading days
            # = worst close relative to entry price (always <= 0)
            window_end = min(pos + DRAWDOWN_WINDOW + 1, len(trading_dates))
            if window_end > pos + 1:
                window_prices = [
                    float(close_by_date[trading_dates[p]])
                    for p in range(pos + 1, window_end)
                ]
                worst = min(window_prices)
                dd = (worst - entry_price) / entry_price * 100.0
                events.at[idx, "max_drawdown_20d"] = round(min(dd, 0.0), 4)

    return events


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_position(trading_dates: list, signal_date) -> int | None:
    """Return the index of signal_date in trading_dates, or the next date.

    Returns None if signal_date is beyond the last available trading date.
    """
    # Binary search for the first date >= signal_date
    lo, hi = 0, len(trading_dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if trading_dates[mid] < signal_date:
            lo = mid + 1
        else:
            hi = mid

    if lo >= len(trading_dates):
        return None          # signal_date is after all available data
    return lo


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    token = FINMIND_TOKEN or None

    # ── Load Step 1 output ────────────────────────────────────────────────────
    if not EVENTS_PATH.exists():
        print(f"\n  ERROR: {EVENTS_PATH} not found.")
        print("  Run scripts/validate_recommendations.py first.\n")
        sys.exit(1)

    events = pd.read_csv(EVENTS_PATH)
    print(f"\n  Loaded {len(events)} recommendation event(s) from Step 1")
    print(f"  Stocks : {sorted(events['stock_id'].astype(str).unique())}\n")

    # ── Attach forward returns ────────────────────────────────────────────────
    print("  Fetching forward price data …\n")
    enriched = add_forward_returns(events, token=token)

    # ── Quick coverage report ─────────────────────────────────────────────────
    print()
    div = "─" * 60
    print(div)
    print(f"  Forward-return coverage")
    print(div)
    for h in HORIZONS:
        col      = f"return_{h}d"
        n_valid  = enriched[col].notna().sum()
        n_total  = len(enriched)
        print(f"  return_{h:>3}d      : {n_valid:>3} / {n_total} events have data")
    col     = "max_drawdown_20d"
    n_valid = enriched[col].notna().sum()
    print(f"  max_drawdown_20d : {n_valid:>3} / {len(enriched)} events have data")
    print()

    # ── Save ──────────────────────────────────────────────────────────────────
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(OUTPUT_PATH, index=False)
    print(f"  Saved → {OUTPUT_PATH}\n")


if __name__ == "__main__":
    main()
