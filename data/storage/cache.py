import logging
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Root cache directory — override by passing cache_dir explicitly
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"

# One sub-directory per data type keeps files organised as more types are added
_DATASET_DIRS = {
    "price": "price",
    "fundamentals": "fundamentals",
    "margin": "margin",
}


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def save(
    df: pd.DataFrame,
    dataset: str,
    stock_id: str,
    cache_dir: Optional[Path] = None,
) -> Path:
    """Persist a DataFrame to a Parquet file.

    Args:
        df:        DataFrame to save.
        dataset:   One of "price", "fundamentals", "margin".
        stock_id:  Taiwan stock ticker (e.g. "2330").
        cache_dir: Root cache directory. Defaults to <project_root>/.cache.

    Returns:
        Path to the written Parquet file.

    Raises:
        ValueError: If dataset is not recognised.
    """
    path = _resolve_path(dataset, stock_id, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    df.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
    logger.debug("Saved %d rows → %s", len(df), path)
    return path


def load(
    dataset: str,
    stock_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    cache_dir: Optional[Path] = None,
) -> Optional[pd.DataFrame]:
    """Load a cached DataFrame from Parquet.

    Args:
        dataset:    One of "price", "fundamentals", "margin".
        stock_id:   Taiwan stock ticker (e.g. "2330").
        start_date: If provided, filter rows where date >= start_date.
        end_date:   If provided, filter rows where date <= end_date.
        cache_dir:  Root cache directory. Defaults to <project_root>/.cache.

    Returns:
        DataFrame, or None if no cache file exists.

    Raises:
        ValueError: If dataset is not recognised.
    """
    path = _resolve_path(dataset, stock_id, cache_dir)

    if not path.exists():
        logger.debug("Cache miss: %s", path)
        return None

    logger.debug("Cache hit: %s", path)
    df = pd.read_parquet(path, engine="pyarrow")

    if "date" in df.columns:
        df = _filter_by_date(df, start_date, end_date)

    return df.reset_index(drop=True)


def invalidate(
    dataset: str,
    stock_id: str,
    cache_dir: Optional[Path] = None,
) -> bool:
    """Delete a cached Parquet file.

    Returns:
        True if the file existed and was deleted, False if it was not found.

    Raises:
        ValueError: If dataset is not recognised.
    """
    path = _resolve_path(dataset, stock_id, cache_dir)

    if not path.exists():
        return False

    path.unlink()
    logger.debug("Invalidated cache: %s", path)
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_path(dataset: str, stock_id: str, cache_dir: Optional[Path]) -> Path:
    if dataset not in _DATASET_DIRS:
        raise ValueError(
            f"Unknown dataset '{dataset}'. "
            f"Valid options: {sorted(_DATASET_DIRS)}"
        )
    root = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
    return root / _DATASET_DIRS[dataset] / f"{stock_id}.parquet"


def _filter_by_date(
    df: pd.DataFrame,
    start_date: Optional[date],
    end_date: Optional[date],
) -> pd.DataFrame:
    col = pd.to_datetime(df["date"]).dt.date
    if start_date:
        df = df[col >= start_date]
    if end_date:
        df = df[col <= end_date]
    return df
