"""Integration test: fetch → validate → cache → load."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from data.fetchers.price import fetch_daily_price
from data.storage.cache import invalidate, load, save
from data.storage.schema import DailyPrice

# ---------------------------------------------------------------------------
# Test parameters
# ---------------------------------------------------------------------------

STOCK_ID = "2330"
START_DATE = date(2024, 1, 1)
END_DATE = date(2024, 1, 31)
EXPECTED_COLUMNS = ["stock_id", "date", "open", "high", "low", "close", "volume"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fetched_df():
    """Fetch once for all tests in this module."""
    return fetch_daily_price(STOCK_ID, start_date=START_DATE, end_date=END_DATE)


@pytest.fixture(scope="module")
def cached_df(fetched_df, tmp_path_factory):
    """Save fetched data to a temp cache and load it back."""
    cache_dir: Path = tmp_path_factory.mktemp("cache")
    save(fetched_df, dataset="price", stock_id=STOCK_ID, cache_dir=cache_dir)
    df = load(dataset="price", stock_id=STOCK_ID, cache_dir=cache_dir)
    yield df
    invalidate(dataset="price", stock_id=STOCK_ID, cache_dir=cache_dir)


# ---------------------------------------------------------------------------
# 1. Fetch
# ---------------------------------------------------------------------------

def test_fetched_df_is_not_empty(fetched_df):
    assert len(fetched_df) > 0


def test_fetched_df_has_expected_columns(fetched_df):
    assert list(fetched_df.columns) == EXPECTED_COLUMNS


def test_fetched_df_contains_correct_stock_id(fetched_df):
    assert fetched_df["stock_id"].unique().tolist() == [STOCK_ID]


def test_fetched_df_dates_within_range(fetched_df):
    assert fetched_df["date"].min() >= START_DATE
    assert fetched_df["date"].max() <= END_DATE


# ---------------------------------------------------------------------------
# 2. Schema validation
# ---------------------------------------------------------------------------

def test_all_rows_pass_schema_validation(fetched_df):
    errors = []
    for row in fetched_df.itertuples(index=False):
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
            errors.append((row.date, exc))

    assert errors == [], f"{len(errors)} row(s) failed validation: {errors[:3]}"


# ---------------------------------------------------------------------------
# 3. Cache round-trip
# ---------------------------------------------------------------------------

def test_cached_df_is_not_none(cached_df):
    assert cached_df is not None


def test_cached_df_shape_matches_fetched(fetched_df, cached_df):
    assert cached_df.shape == fetched_df.shape


def test_cached_df_columns_match(cached_df):
    assert list(cached_df.columns) == EXPECTED_COLUMNS


def test_cached_close_prices_match_fetched(fetched_df, cached_df):
    assert cached_df["close"].tolist() == fetched_df["close"].tolist()


def test_cached_volumes_match_fetched(fetched_df, cached_df):
    assert cached_df["volume"].tolist() == fetched_df["volume"].tolist()
