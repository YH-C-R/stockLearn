"""Demo: margin-trend strategy on a single Taiwan stock."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from config.credentials import FINMIND_TOKEN
from data.fetchers.margin import fetch_margin_data
from data.fetchers.price import fetch_daily_price
from signals.base import SignalDirection
from strategies.margin_trend import MarginTrendStrategy

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STOCK_ID   = "2330"
START_DATE = date(2024, 1, 1)
END_DATE   = date(2024, 12, 31)
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'─' * 55}\n  {title}\n{'─' * 55}")


def print_signals(signals: list, latest_n: int = 10) -> None:
    if not signals:
        print("  No signals generated.")
        return

    print(f"  Total signals : {len(signals)}")
    for direction in (SignalDirection.BULLISH, SignalDirection.BEARISH, SignalDirection.NEUTRAL):
        count = sum(1 for s in signals if s.direction == direction)
        if count:
            print(f"    {direction.value:<10} : {count}")

    print(f"\n  Latest {min(latest_n, len(signals))} signals:\n")
    header = (
        f"  {'Date':<12} {'Score':>6}  {'Direction':<10}"
        f"  {'Close':>8}  {'Price Chg%':>10}  {'Margin Chg%':>11}  {'Margin Bal':>12}"
    )
    print(header)
    print("  " + "─" * (len(header) - 2))
    for s in signals[-latest_n:]:
        meta = s.metadata or {}
        print(
            f"  {str(s.date):<12}"
            f" {s.score:>+6.2f}"
            f"  {s.direction.value:<10}"
            f"  {meta.get('close', 0):>8.2f}"
            f"  {meta.get('price_change_pct', 0):>+10.2f}"
            f"  {meta.get('margin_change_pct', 0):>+11.2f}"
            f"  {meta.get('margin_purchase_balance', 0):>12,}"
        )


def plot_and_save(
    price_df: pd.DataFrame,
    margin_df: pd.DataFrame,
    signals: list,
    stock_id: str,
    out_dir: Path,
) -> None:
    bullish_dates = {s.date for s in signals if s.direction == SignalDirection.BULLISH}
    bearish_dates = {s.date for s in signals if s.direction == SignalDirection.BEARISH}

    price_plot  = price_df.copy()
    margin_plot = margin_df.copy()
    price_plot["date"]  = pd.to_datetime(price_plot["date"])
    margin_plot["date"] = pd.to_datetime(margin_plot["date"])

    price_idx = price_plot.set_index("date")

    def marker_series(dates):
        xs = pd.to_datetime(list(dates))
        matched = price_idx.reindex(xs)
        return matched.index, matched["close"]

    fig, (ax_price, ax_margin) = plt.subplots(
        2, 1,
        figsize=(14, 7),
        gridspec_kw={"height_ratios": [3, 2]},
        sharex=True,
    )
    fig.suptitle(
        f"{stock_id}  |  Margin Trend Strategy  |  {START_DATE} → {END_DATE}",
        fontsize=12, fontweight="bold",
    )

    # — Closing price + signal markers -------------------------------------
    ax_price.plot(price_plot["date"], price_plot["close"],
                  color="#aec7e8", linewidth=1.0, zorder=1, label="Close")

    if bullish_dates:
        xs, ys = marker_series(bullish_dates)
        ax_price.scatter(xs, ys, color="#2ca02c", marker="^",
                         s=80, zorder=3, label="Bullish")
    if bearish_dates:
        xs, ys = marker_series(bearish_dates)
        ax_price.scatter(xs, ys, color="#d62728", marker="v",
                         s=80, zorder=3, label="Bearish")

    ax_price.set_ylabel("Close (TWD)")
    ax_price.legend(fontsize=8, loc="upper left")
    ax_price.grid(axis="y", linestyle="--", alpha=0.35)
    ax_price.set_title("Closing Price with Signal Markers", fontsize=10, loc="left")

    # — Margin purchase balance --------------------------------------------
    merged = pd.merge(price_plot[["date"]], margin_plot[["date", "margin_purchase_balance"]],
                      on="date", how="left")
    ax_margin.fill_between(merged["date"],
                           merged["margin_purchase_balance"] / 1_000,
                           alpha=0.4, color="#1f77b4")
    ax_margin.plot(merged["date"],
                   merged["margin_purchase_balance"] / 1_000,
                   color="#1f77b4", linewidth=1.0, label="Margin Balance (K shares)")

    # Mark signal days on margin panel
    all_sig_dates = pd.to_datetime(list(bullish_dates | bearish_dates))
    matched_margin = merged.set_index("date").reindex(all_sig_dates)
    if not matched_margin.empty:
        colors = [
            "#2ca02c" if d.date() in bullish_dates else "#d62728"
            for d in matched_margin.index
        ]
        ax_margin.scatter(matched_margin.index,
                          matched_margin["margin_purchase_balance"] / 1_000,
                          color=colors, s=50, zorder=3)

    ax_margin.set_ylabel("Margin Balance (K shares)")
    ax_margin.set_xlabel("Date")
    ax_margin.legend(fontsize=8, loc="upper left")
    ax_margin.grid(axis="y", linestyle="--", alpha=0.35)
    ax_margin.set_title("Margin Purchase Balance", fontsize=10, loc="left")

    ax_margin.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_margin.xaxis.set_major_locator(mdates.MonthLocator())
    fig.autofmt_xdate(rotation=30)

    plt.tight_layout()

    out_path = out_dir / f"{stock_id}_margin_trend.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Chart saved → {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    token = FINMIND_TOKEN or None

    # 1. Fetch ----------------------------------------------------------------
    section(f"1. Fetching  {STOCK_ID}  {START_DATE} → {END_DATE}")
    price_df  = fetch_daily_price(STOCK_ID, START_DATE, END_DATE, token=token)
    margin_df = fetch_margin_data(STOCK_ID, START_DATE, END_DATE, token=token)
    print(f"  Price rows  : {len(price_df)}")
    print(f"  Margin rows : {len(margin_df)}")

    # 2. Run strategy ---------------------------------------------------------
    section("2. Running MarginTrendStrategy")
    strategy = MarginTrendStrategy(
        window=5,
        surge_threshold=0.05,
        unwind_threshold=0.03,
        min_abs_score=0.3,
    )
    print(
        f"  window={strategy.window}  "
        f"surge_threshold={strategy.surge_threshold}  "
        f"unwind_threshold={strategy.unwind_threshold}  "
        f"min_abs_score={strategy.min_abs_score}"
    )
    signals = strategy.generate(price_df, margin_df=margin_df)

    # 3. Print results --------------------------------------------------------
    section("3. Signal summary")
    print_signals(signals)

    # 4. Chart ----------------------------------------------------------------
    section("4. Generating chart")
    plot_and_save(price_df, margin_df, signals, STOCK_ID, OUTPUT_DIR)

    section("Done")


if __name__ == "__main__":
    main()
