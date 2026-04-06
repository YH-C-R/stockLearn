from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from data.storage.cache import invalidate, load, save


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_cache(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "stock_id": ["2330", "2330", "2330"],
            "date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
            "open":   [560.0, 562.0, 558.0],
            "high":   [575.0, 570.0, 565.0],
            "low":    [558.0, 555.0, 550.0],
            "close":  [570.0, 565.0, 560.0],
            "volume": [25_000_000, 18_000_000, 20_000_000],
        }
    )


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------

def test_save_creates_parquet_file(sample_df, tmp_cache):
    path = save(sample_df, dataset="price", stock_id="2330", cache_dir=tmp_cache)
    assert path.exists()
    assert path.suffix == ".parquet"


def test_load_returns_same_shape(sample_df, tmp_cache):
    save(sample_df, dataset="price", stock_id="2330", cache_dir=tmp_cache)
    df_loaded = load(dataset="price", stock_id="2330", cache_dir=tmp_cache)

    assert df_loaded is not None
    assert df_loaded.shape == sample_df.shape


def test_load_returns_same_values(sample_df, tmp_cache):
    save(sample_df, dataset="price", stock_id="2330", cache_dir=tmp_cache)
    df_loaded = load(dataset="price", stock_id="2330", cache_dir=tmp_cache)

    assert list(df_loaded.columns) == list(sample_df.columns)
    assert df_loaded["close"].tolist() == sample_df["close"].tolist()
    assert df_loaded["volume"].tolist() == sample_df["volume"].tolist()


# ---------------------------------------------------------------------------
# Cache miss
# ---------------------------------------------------------------------------

def test_load_returns_none_when_no_cache(tmp_cache):
    result = load(dataset="price", stock_id="9999", cache_dir=tmp_cache)
    assert result is None


# ---------------------------------------------------------------------------
# Date filtering
# ---------------------------------------------------------------------------

def test_load_with_date_filter(sample_df, tmp_cache):
    save(sample_df, dataset="price", stock_id="2330", cache_dir=tmp_cache)
    df_filtered = load(
        dataset="price",
        stock_id="2330",
        start_date=date(2024, 1, 3),
        end_date=date(2024, 1, 3),
        cache_dir=tmp_cache,
    )
    assert df_filtered is not None
    assert len(df_filtered) == 1
    assert df_filtered.iloc[0]["close"] == 565.0


# ---------------------------------------------------------------------------
# invalidate
# ---------------------------------------------------------------------------

def test_invalidate_removes_file(sample_df, tmp_cache):
    path = save(sample_df, dataset="price", stock_id="2330", cache_dir=tmp_cache)
    assert path.exists()

    removed = invalidate(dataset="price", stock_id="2330", cache_dir=tmp_cache)
    assert removed is True
    assert not path.exists()


def test_invalidate_returns_false_when_no_cache(tmp_cache):
    assert invalidate(dataset="price", stock_id="9999", cache_dir=tmp_cache) is False


# ---------------------------------------------------------------------------
# Unknown dataset
# ---------------------------------------------------------------------------

def test_unknown_dataset_raises(sample_df, tmp_cache):
    with pytest.raises(ValueError, match="Unknown dataset"):
        save(sample_df, dataset="unknown_type", stock_id="2330", cache_dir=tmp_cache)
