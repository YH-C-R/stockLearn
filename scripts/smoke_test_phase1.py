"""Phase 1 smoke test — fetcher → schema → cache → plot."""

import sys
from datetime import date
from pathlib import Path

# Allow running from the project root: python scripts/smoke_test_phase1.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import pandas as pd
from pydantic import ValidationError

from config import settings
from config.credentials import FINMIND_TOKEN
from data.fetchers.price import fetch_daily_price
from data.storage.cache import invalidate, load, save
from data.storage.schema import DailyPrice

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STOCK_ID = "2330"
START_DATE = date(2024, 1, 1)
END_DATE = date(2024, 12, 31)
DATASET = "price"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print(f"{'─' * 55}")


def validate_schema(df: pd.DataFrame) -> None:
    errors = 0
    for row in df.itertuples(index=False):
        try:
            DailyPrice(
                stock_id=row.stock_id,
                date=row.date,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
            )
        except ValidationError as exc:
            print(f"  [WARN] Validation failed for {row.date}: {exc.errors(include_url=False)}")
            errors += 1

    if errors:
        print(f"  {errors} row(s) failed validation.")
    else:
        print(f"  All {len(df)} rows passed schema validation.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # ------------------------------------------------------------------
    # 1. Fetch
    # ------------------------------------------------------------------
    section(f"1. Fetching {STOCK_ID}  {START_DATE} → {END_DATE}")
    token = getattr(settings, "FINMIND_TOKEN", None) or FINMIND_TOKEN
    df: pd.DataFrame = fetch_daily_price(
        stock_id=STOCK_ID,
        start_date=START_DATE,
        end_date=END_DATE,
        token=token or None,
    )
    print(f"  Fetched {len(df)} rows")

    # ------------------------------------------------------------------
    # 2. Schema validation
    # ------------------------------------------------------------------
    section("2. Schema validation")
    validate_schema(df)

    # ------------------------------------------------------------------
    # 3. DataFrame info
    # ------------------------------------------------------------------
    section("3. DataFrame info")
    print(f"  Shape  : {df.shape}")
    print(f"  Columns: {list(df.columns)}")
    print(f"\n  First 5 rows:\n")
    print(df.head().to_string(index=False))

    # ------------------------------------------------------------------
    # 4. Save to cache
    # ------------------------------------------------------------------
    section("4. Saving to local Parquet cache")
    cache_path = save(df, dataset=DATASET, stock_id=STOCK_ID)
    print(f"  Saved → {cache_path}")

    # ------------------------------------------------------------------
    # 5. Load from cache
    # ------------------------------------------------------------------
    section("5. Loading from cache")
    df_cached = load(dataset=DATASET, stock_id=STOCK_ID, start_date=START_DATE, end_date=END_DATE)

    if df_cached is None:
        print("  [ERROR] Cache load returned None — file not found.")
        sys.exit(1)

    match = df_cached.shape == df.shape
    print(f"  Loaded {len(df_cached)} rows  (shape match: {match})")

    # ------------------------------------------------------------------
    # 6. Plot
    # ------------------------------------------------------------------
    section("6. Plotting")

    df_plot = df_cached.copy()
    df_plot["date"] = pd.to_datetime(df_plot["date"])

    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1,
        figsize=(12, 7),
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
    )
    fig.suptitle(f"{STOCK_ID}  |  {START_DATE} → {END_DATE}", fontsize=13, fontweight="bold")

    # Closing price
    ax_price.plot(df_plot["date"], df_plot["close"], color="#1f77b4", linewidth=1.2)
    ax_price.set_ylabel("Close (TWD)")
    ax_price.grid(axis="y", linestyle="--", alpha=0.4)
    ax_price.set_title("Closing Price", fontsize=10, loc="left")

    # Volume
    ax_vol.bar(df_plot["date"], df_plot["volume"] / 1_000, color="#aec7e8", width=1.5)
    ax_vol.set_ylabel("Volume (K shares)")
    ax_vol.set_xlabel("Date")
    ax_vol.grid(axis="y", linestyle="--", alpha=0.4)
    ax_vol.set_title("Volume", fontsize=10, loc="left")

    plt.tight_layout()

    plot_path = Path(__file__).parent / f"smoke_test_{STOCK_ID}.png"
    plt.savefig(plot_path, dpi=150)
    print(f"  Chart saved → {plot_path}")
    plt.show()

    section("Smoke test passed")

    # Clean up cache entry created by this test
    invalidate(dataset=DATASET, stock_id=STOCK_ID)


if __name__ == "__main__":
    main()
