"""Demo: Davis Double strategy on a single Taiwan stock."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from config.credentials import FINMIND_TOKEN
from data.fetchers.fundamentals import fetch_eps_data
from data.fetchers.price import fetch_daily_price
from signals.base import SignalDirection
from strategies.davis_double import (
    DavisDoubleStrategy,
    _add_yoy_growth,
    _align_to_daily,
    _effective_date,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STOCK_ID   = "2330"
# Price window: current year only
START_DATE = date(2024, 1, 1)
END_DATE   = date(2024, 12, 31)
# Fundamentals need ~5 quarters of history for YoY (4 prior + current)
FUND_START = date(2022, 1, 1)

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'─' * 55}\n  {title}\n{'─' * 55}")


def print_aligned_sample(aligned_df: pd.DataFrame, n: int = 8) -> None:
    """Print a sample of daily rows showing the forward-filled EPS."""
    cols = ["date", "close", "report_period", "eps", "yoy_growth"]
    available = [c for c in cols if c in aligned_df.columns]
    # Pick rows where EPS just changed (first day of each new quarter forward-fill)
    eps_change = aligned_df["report_period"].ne(aligned_df["report_period"].shift())
    sample = aligned_df[eps_change][available].dropna(subset=["eps"]).head(n)
    if sample.empty:
        print("  No aligned rows to display.")
        return
    sample = sample.copy()
    if "yoy_growth" in sample.columns:
        sample["yoy_growth"] = sample["yoy_growth"].map(
            lambda x: f"{x*100:+.1f}%" if pd.notna(x) else "N/A"
        )
    print(sample.to_string(index=False))


def print_signals(signals: list, latest_n: int = 10) -> None:
    if not signals:
        print("  No signals generated.")
        return

    print(f"  Total signals : {len(signals)}")
    print(f"\n  Latest {min(latest_n, len(signals))} signals:\n")
    header = (
        f"  {'Date':<12} {'Score':>6}  {'EPS':>6}  "
        f"{'YoY%':>7}  {'Close':>8}  {'MA':>8}  {'Q Period':<12}"
    )
    print(header)
    print("  " + "─" * (len(header) - 2))
    for s in signals[-latest_n:]:
        meta = s.metadata or {}
        print(
            f"  {str(s.date):<12}"
            f" {s.score:>+6.2f}"
            f"  {meta.get('eps', 0):>6.2f}"
            f"  {meta.get('yoy_growth_pct', 0):>+6.1f}%"
            f"  {meta.get('close', 0):>8.2f}"
            f"  {meta.get('ma', 0):>8.2f}"
            f"  {meta.get('report_period', ''):<12}"
        )


def plot_and_save(
    aligned_df: pd.DataFrame,
    signals: list,
    stock_id: str,
    out_dir: Path,
) -> None:
    sig_dates = {s.date for s in signals}

    df_plot = aligned_df.dropna(subset=["eps"]).copy()
    df_plot["date"] = pd.to_datetime(df_plot["date"])
    price_idx = df_plot.set_index("date")

    # Build quarterly EPS bar data (one value per quarter)
    eps_quarters = (
        df_plot.dropna(subset=["report_period"])
        .drop_duplicates(subset=["report_period"])
        .set_index(pd.to_datetime(df_plot.dropna(subset=["report_period"])
                                         .drop_duplicates(subset=["report_period"])["date"]))
    )

    fig, (ax_price, ax_eps) = plt.subplots(
        2, 1,
        figsize=(14, 7),
        gridspec_kw={"height_ratios": [3, 2]},
        sharex=True,
    )
    fig.suptitle(
        f"{stock_id}  |  Davis Double Strategy  |  {START_DATE} → {END_DATE}",
        fontsize=12, fontweight="bold",
    )

    # — Closing price + MA --------------------------------------------------
    ma = df_plot["close"].rolling(60).mean()
    ax_price.plot(df_plot["date"], df_plot["close"],
                  color="#aec7e8", linewidth=1.0, label="Close", zorder=1)
    ax_price.plot(df_plot["date"], ma,
                  color="#ff7f0e", linewidth=1.0, linestyle="--",
                  label="MA60 (PE proxy)", zorder=2)

    # — Signal markers -------------------------------------------------------
    if sig_dates:
        xs = pd.to_datetime(list(sig_dates))
        ys = price_idx.reindex(xs)["close"]
        ax_price.scatter(xs, ys, color="#2ca02c", marker="^",
                         s=80, zorder=4, label="Davis Double signal")

    ax_price.set_ylabel("Close (TWD)")
    ax_price.legend(fontsize=8, loc="upper left")
    ax_price.grid(axis="y", linestyle="--", alpha=0.35)
    ax_price.set_title("Closing Price + MA60", fontsize=10, loc="left")

    # — EPS bar chart (forward-filled to daily, coloured by YoY) -----------
    colors = df_plot["yoy_growth"].apply(
        lambda g: "#2ca02c" if (pd.notna(g) and g > 0) else "#d62728"
    )
    ax_eps.fill_between(df_plot["date"], df_plot["eps"],
                        alpha=0.25, color="#1f77b4")
    ax_eps.plot(df_plot["date"], df_plot["eps"],
                color="#1f77b4", linewidth=1.0, label="EPS (forward-filled)")
    ax_eps.axhline(0, color="black", linewidth=0.6)

    ax_eps.set_ylabel("EPS (TWD)")
    ax_eps.set_xlabel("Date")
    ax_eps.legend(fontsize=8, loc="upper left")
    ax_eps.grid(axis="y", linestyle="--", alpha=0.35)
    ax_eps.set_title("Quarterly EPS (forward-filled, point-in-time)", fontsize=10, loc="left")

    ax_eps.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_eps.xaxis.set_major_locator(mdates.MonthLocator())
    fig.autofmt_xdate(rotation=30)

    plt.tight_layout()
    out_path = out_dir / f"{stock_id}_davis_double.png"
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
    section(f"1. Fetching price  {STOCK_ID}  {START_DATE} → {END_DATE}")
    price_df = fetch_daily_price(STOCK_ID, START_DATE, END_DATE, token=token)
    print(f"  {len(price_df)} rows fetched.")

    section(f"2. Fetching fundamentals  {STOCK_ID}  {FUND_START} → {END_DATE}")
    fund_df = fetch_eps_data(STOCK_ID, FUND_START, END_DATE, token=token)
    print(f"  {len(fund_df)} quarters fetched.")
    print(f"\n  Raw fundamentals:\n")
    print(fund_df.to_string(index=False))

    # 2. Alignment preview ---------------------------------------------------
    section("3. Alignment preview (EPS → daily dates)")
    fund_df["effective_date"] = fund_df.apply(_effective_date, axis=1)
    fund_with_yoy = _add_yoy_growth(fund_df)

    print(f"  {'report_period':<14} {'effective_date':<16} {'eps':>6}  {'yoy_growth':>10}")
    print("  " + "─" * 50)
    for row in fund_with_yoy.itertuples(index=False):
        yoy = f"{row.yoy_growth*100:+.1f}%" if pd.notna(row.yoy_growth) else "  N/A"
        print(
            f"  {str(row.report_period):<14}"
            f" {str(row.effective_date):<16}"
            f" {row.eps:>6.2f}"
            f"  {yoy:>10}"
        )

    aligned_df = _align_to_daily(price_df, fund_with_yoy)

    section("4. Sample aligned daily rows (first day of each new quarter)")
    print_aligned_sample(aligned_df)

    # 3. Run strategy --------------------------------------------------------
    section("5. Running DavisDoubleStrategy")
    strategy = DavisDoubleStrategy(
        ma_window=60,
        yoy_threshold=0.30,
    )
    print(
        f"  ma_window={strategy.ma_window}  "
        f"yoy_threshold={strategy.yoy_threshold:.0%}"
    )
    signals = strategy.generate(price_df, fundamentals_df=fund_df)

    # 4. Print results -------------------------------------------------------
    section("6. Signal summary")
    print_signals(signals)

    # 5. Chart ---------------------------------------------------------------
    section("7. Generating chart")
    plot_and_save(aligned_df, signals, STOCK_ID, OUTPUT_DIR)

    section("Done")


if __name__ == "__main__":
    main()
