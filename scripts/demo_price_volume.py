"""Demo: price-volume strategy on a single Taiwan stock."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from config.credentials import FINMIND_TOKEN
from data.fetchers.price import fetch_daily_price
from signals.base import SignalDirection
from strategies.price_volume import PriceVolumeStrategy

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


def print_signals(signals, latest_n: int = 10) -> None:
    if not signals:
        print("  No signals generated.")
        return

    print(f"  Total signals : {len(signals)}")

    by_score = {1.0: "strong_surge", 0.8: "surge", 0.4: "unconfirmed"}
    for score, label in by_score.items():
        count = sum(1 for s in signals if s.score == score)
        print(f"    score={score:+.1f} ({label:>20}) : {count}")

    print(f"\n  Latest {min(latest_n, len(signals))} signals:\n")
    header = f"  {'Date':<12} {'Score':>6}  {'Close':>8}  {'Vol Ratio':>9}  Confirmation"
    print(header)
    print("  " + "─" * (len(header) - 2))
    for s in signals[-latest_n:]:
        meta  = s.metadata or {}
        print(
            f"  {str(s.date):<12}"
            f" {s.score:>+6.1f}"
            f"  {s.signal_value:>8.2f}"
            f"  {meta.get('volume_ratio', 0):>9.2f}"
            f"  {meta.get('confirmation', '')}"
        )


def plot_and_save(df: pd.DataFrame, signals, stock_id: str, out_dir: Path) -> None:
    sig_dates   = {s.date for s in signals}
    strong_dates = {s.date for s in signals if s.score == 1.0}
    surge_dates  = {s.date for s in signals if s.score == 0.8}
    weak_dates   = {s.date for s in signals if s.score == 0.4}

    df_plot = df.copy()
    df_plot["date"] = pd.to_datetime(df_plot["date"])
    date_index = df_plot.set_index("date")

    def marker_series(dates):
        dt = pd.to_datetime(list(dates))
        matched = date_index.reindex(dt)
        return matched.index, matched["close"]

    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1,
        figsize=(14, 7),
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
    )
    fig.suptitle(
        f"{stock_id}  |  Price-Volume Strategy  |  {START_DATE} → {END_DATE}",
        fontsize=12, fontweight="bold",
    )

    # — Closing price line ------------------------------------------------
    ax_price.plot(df_plot["date"], df_plot["close"],
                  color="#aec7e8", linewidth=1.0, zorder=1, label="Close")

    # — Signal markers ----------------------------------------------------
    for dates, color, marker, label, size, zorder in [
        (strong_dates, "#d62728", "*", "Score +1.0 (strong surge)", 160, 4),
        (surge_dates,  "#ff7f0e", "^", "Score +0.8 (surge)",        80,  3),
        (weak_dates,   "#9467bd", "o", "Score +0.4 (unconfirmed)",   50,  2),
    ]:
        if dates:
            xs, ys = marker_series(dates)
            ax_price.scatter(xs, ys, color=color, marker=marker,
                             s=size, zorder=zorder, label=label)

    ax_price.set_ylabel("Close (TWD)")
    ax_price.legend(fontsize=8, loc="upper left")
    ax_price.grid(axis="y", linestyle="--", alpha=0.35)
    ax_price.set_title("Closing Price with Signal Markers", fontsize=10, loc="left")

    # — Volume bars, signal days highlighted ------------------------------
    bar_colors = [
        "#d62728" if d.date() in sig_dates else "#c7c7c7"
        for d in df_plot["date"]
    ]
    ax_vol.bar(df_plot["date"], df_plot["volume"] / 1_000,
               color=bar_colors, width=1.5)
    ax_vol.set_ylabel("Volume (K shares)")
    ax_vol.set_xlabel("Date")
    ax_vol.grid(axis="y", linestyle="--", alpha=0.35)
    ax_vol.set_title("Volume  (red = signal day)", fontsize=10, loc="left")

    ax_vol.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_vol.xaxis.set_major_locator(mdates.MonthLocator())
    fig.autofmt_xdate(rotation=30)

    plt.tight_layout()

    out_path = out_dir / f"{stock_id}_price_volume.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Chart saved → {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Fetch ------------------------------------------------------------
    section(f"1. Fetching  {STOCK_ID}  {START_DATE} → {END_DATE}")
    df = fetch_daily_price(
        stock_id=STOCK_ID,
        start_date=START_DATE,
        end_date=END_DATE,
        token=FINMIND_TOKEN or None,
    )
    print(f"  {len(df)} rows fetched.")

    # 2. Run strategy -----------------------------------------------------
    section("2. Running PriceVolumeStrategy")
    strategy = PriceVolumeStrategy()
    print(
        f"  price_window={strategy.price_window}  "
        f"volume_window={strategy.volume_window}  "
        f"volume_surge_mult={strategy.volume_surge_mult}×"
    )
    signals = strategy.generate(df)

    # 3. Print results ----------------------------------------------------
    section("3. Signal summary")
    print_signals(signals)

    # 4. Chart ------------------------------------------------------------
    section("4. Generating chart")
    plot_and_save(df, signals, STOCK_ID, OUTPUT_DIR)

    section("Done")


if __name__ == "__main__":
    main()
