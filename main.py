"""Phase 1 demo entry point — fetch, validate, cache, summarise, chart."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from pydantic import ValidationError

from config import settings
from config.credentials import FINMIND_TOKEN
from data.fetchers.price import fetch_daily_price
from data.storage.cache import load, save
from data.storage.schema import DailyPrice

# ---------------------------------------------------------------------------
# Run config
# ---------------------------------------------------------------------------

STOCK_ID = "2330"
START_DATE = date(2024, 1, 1)
END_DATE = date(2024, 12, 31)

OUTPUT_DIR = Path("outputs")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    width = 58
    print(f"\n{'─' * width}")
    print(f"  {title}")
    print(f"{'─' * width}")


def validate_schema(df: pd.DataFrame) -> int:
    """Validate every row against DailyPrice. Returns count of failed rows."""
    failures = 0
    for row in df.itertuples(index=False):
        try:
            DailyPrice(
                stock_id=row.stock_id,
                date=row.date,
                open=Decimal(str(row.open)),
                high=Decimal(str(row.high)),
                low=Decimal(str(row.low)),
                close=Decimal(str(row.close)),
                volume=int(row.volume),
            )
        except ValidationError as exc:
            print(f"  [WARN] {row.date}: {exc.errors(include_url=False)}")
            failures += 1
    return failures


def print_summary(df: pd.DataFrame) -> None:
    close = df["close"]
    volume = df["volume"]
    print(f"  Rows         : {len(df)}")
    print(f"  Columns      : {list(df.columns)}")
    print(f"  Date range   : {df['date'].min()}  →  {df['date'].max()}")
    print(f"  Close  (TWD) : min={close.min():.2f}  max={close.max():.2f}  "
          f"mean={close.mean():.2f}")
    print(f"  Volume (K)   : min={volume.min()//1000:,}  max={volume.max()//1000:,}  "
          f"mean={int(volume.mean())//1000:,}")
    print(f"\n  First 5 rows:\n")
    print(df.head().to_string(index=False))


def plot_and_save(df: pd.DataFrame, stock_id: str, out_dir: Path) -> None:
    df_plot = df.copy()
    df_plot["date"] = pd.to_datetime(df_plot["date"])

    ma5  = df_plot["close"].rolling(settings.MA_SHORT_WINDOW).mean()
    ma20 = df_plot["close"].rolling(settings.MA_LONG_WINDOW).mean()

    fig, axes = plt.subplots(
        3, 1,
        figsize=(13, 9),
        gridspec_kw={"height_ratios": [3, 1, 1]},
        sharex=True,
    )
    fig.suptitle(
        f"{stock_id}  |  {START_DATE} → {END_DATE}",
        fontsize=13, fontweight="bold",
    )

    # — Closing price + MAs ------------------------------------------------
    ax_price = axes[0]
    ax_price.plot(df_plot["date"], df_plot["close"],
                  color="#1f77b4", linewidth=1.2, label="Close")
    ax_price.plot(df_plot["date"], ma5,
                  color="#ff7f0e", linewidth=1.0, linestyle="--",
                  label=f"MA{settings.MA_SHORT_WINDOW}")
    ax_price.plot(df_plot["date"], ma20,
                  color="#2ca02c", linewidth=1.0, linestyle="--",
                  label=f"MA{settings.MA_LONG_WINDOW}")
    ax_price.set_ylabel("Close (TWD)")
    ax_price.legend(fontsize=8)
    ax_price.grid(axis="y", linestyle="--", alpha=0.4)
    ax_price.set_title("Closing Price & Moving Averages", fontsize=10, loc="left")

    # — Volume -------------------------------------------------------------
    ax_vol = axes[1]
    ax_vol.bar(df_plot["date"], df_plot["volume"] / 1_000,
               color="#aec7e8", width=1.5)
    ax_vol.set_ylabel("Volume (K)")
    ax_vol.grid(axis="y", linestyle="--", alpha=0.4)
    ax_vol.set_title("Volume", fontsize=10, loc="left")

    # — Daily return -------------------------------------------------------
    ax_ret = axes[2]
    daily_return = df_plot["close"].pct_change() * 100
    colors = ["#d62728" if r >= 0 else "#2ca02c" for r in daily_return]
    ax_ret.bar(df_plot["date"], daily_return, color=colors, width=1.5)
    ax_ret.axhline(0, color="black", linewidth=0.6)
    ax_ret.set_ylabel("Return (%)")
    ax_ret.set_xlabel("Date")
    ax_ret.grid(axis="y", linestyle="--", alpha=0.4)
    ax_ret.set_title("Daily Return", fontsize=10, loc="left")

    ax_ret.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_ret.xaxis.set_major_locator(mdates.MonthLocator())
    fig.autofmt_xdate(rotation=30)

    plt.tight_layout()

    out_path = out_dir / f"{stock_id}_phase1.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Chart saved → {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(settings.CACHE_DIR)

    # 1. Fetch ------------------------------------------------------------
    section(f"1. Fetching  {STOCK_ID}  {START_DATE} → {END_DATE}")
    token = FINMIND_TOKEN or None
    df = fetch_daily_price(
        stock_id=STOCK_ID,
        start_date=START_DATE,
        end_date=END_DATE,
        token=token,
    )
    print(f"  Fetched {len(df)} rows from FinMind.")

    # 2. Schema validation ------------------------------------------------
    section("2. Schema validation")
    failures = validate_schema(df)
    if failures:
        print(f"  {failures} row(s) failed — see warnings above.")
    else:
        print(f"  All {len(df)} rows passed.")

    # 3. Cache ------------------------------------------------------------
    section("3. Caching to Parquet")
    cache_path = save(df, dataset="price", stock_id=STOCK_ID, cache_dir=cache_dir)
    print(f"  Saved → {cache_path}")

    section("4. Loading from cache")
    df_cached = load(
        dataset="price",
        stock_id=STOCK_ID,
        start_date=START_DATE,
        end_date=END_DATE,
        cache_dir=cache_dir,
    )
    if df_cached is None:
        print("  [ERROR] Cache load returned None.")
        return
    match = df_cached.shape == df.shape
    print(f"  Loaded {len(df_cached)} rows  (shape match with fetched: {match})")

    # 4. Summary ----------------------------------------------------------
    section("5. Data summary")
    print_summary(df_cached)

    # 5. Charts -----------------------------------------------------------
    section("6. Generating charts")
    plot_and_save(df_cached, STOCK_ID, OUTPUT_DIR)

    section("Done")


if __name__ == "__main__":
    main()
