import logging
from datetime import date
from typing import Optional

import pandas as pd
import requests
from pydantic import ValidationError

from data.storage.schema import DailyPrice

logger = logging.getLogger(__name__)

_FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
_DATASET = "TaiwanStockPrice"

# FinMind response column → DailyPrice field
_COLUMN_MAP = {
    "stock_id": "stock_id",
    "date": "date",
    "open": "open",
    "max": "high",
    "min": "low",
    "close": "close",
    "Trading_Volume": "volume",
}

_DTYPE_MAP = {
    "stock_id": str,
    "open": float,
    "high": float,
    "low": float,
    "close": float,
    "volume": int,
}


def fetch_daily_price(
    stock_id: str,
    start_date: date,
    end_date: Optional[date] = None,
    token: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch daily OHLCV data for a Taiwan stock from FinMind.

    Args:
        stock_id:   Taiwan stock ticker (e.g. "2330").
        start_date: Inclusive start date.
        end_date:   Inclusive end date. Defaults to today.
        token:      FinMind API token. Unauthenticated requests are rate-limited.

    Returns:
        DataFrame with columns: stock_id, date, open, high, low, close, volume.
        Rows that fail schema validation are dropped with a warning.

    Raises:
        requests.HTTPError: On non-2xx responses.
        ValueError: If the API returns no data for the given parameters.
    """
    if end_date is None:
        end_date = date.today()

    params: dict = {
        "dataset": _DATASET,
        "data_id": stock_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    if token:
        params["token"] = token

    logger.debug("GET %s params=%s", _FINMIND_URL, params)
    response = requests.get(_FINMIND_URL, params=params, timeout=30)
    response.raise_for_status()

    payload = response.json()
    records = payload.get("data", [])

    if not records:
        raise ValueError(
            f"No price data returned for {stock_id} "
            f"({start_date} – {end_date}). "
            "Check the stock_id and date range."
        )

    df = pd.DataFrame(records)
    df = _normalize(df, stock_id)
    df = _validate_rows(df)
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(df: pd.DataFrame, stock_id: str) -> pd.DataFrame:
    """Rename columns, cast types, and sort by date."""
    missing = set(_COLUMN_MAP.keys()) - set(df.columns)
    if missing:
        raise ValueError(f"FinMind response missing expected columns: {missing}")

    df = df[list(_COLUMN_MAP.keys())].rename(columns=_COLUMN_MAP)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["stock_id"] = stock_id  # normalise in case response omits it

    for col, dtype in _DTYPE_MAP.items():
        df[col] = df[col].astype(dtype)

    return df.sort_values("date")


def _validate_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows that fail DailyPrice validation, logging each failure."""
    valid_mask = []
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
            valid_mask.append(True)
        except ValidationError as exc:
            logger.warning(
                "Dropping invalid row for %s on %s: %s",
                row.stock_id,
                row.date,
                exc.errors(include_url=False),
            )
            valid_mask.append(False)

    return df[valid_mask]
