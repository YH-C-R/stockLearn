from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

from data.fetchers.price import fetch_daily_price

# ---------------------------------------------------------------------------
# Shared FinMind-shaped response payload
# ---------------------------------------------------------------------------

_FINMIND_RECORDS = [
    {
        "stock_id": "2330",
        "date": "2024-01-02",
        "open": "560.0",
        "max": "575.0",
        "min": "558.0",
        "close": "570.0",
        "Trading_Volume": "25000000",
    },
    {
        "stock_id": "2330",
        "date": "2024-01-03",
        "open": "562.0",
        "max": "570.0",
        "min": "555.0",
        "close": "565.0",
        "Trading_Volume": "18000000",
    },
]

_EXPECTED_COLUMNS = ["stock_id", "date", "open", "high", "low", "close", "volume"]


def _mock_response(records: list) -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = {"data": records}
    return mock


# ---------------------------------------------------------------------------
# Column contract
# ---------------------------------------------------------------------------

@patch("data.fetchers.price.requests.get")
def test_returned_dataframe_has_expected_columns(mock_get):
    mock_get.return_value = _mock_response(_FINMIND_RECORDS)

    df = fetch_daily_price("2330", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))

    assert list(df.columns) == _EXPECTED_COLUMNS


# ---------------------------------------------------------------------------
# Non-empty result
# ---------------------------------------------------------------------------

@patch("data.fetchers.price.requests.get")
def test_returned_dataframe_is_not_empty(mock_get):
    mock_get.return_value = _mock_response(_FINMIND_RECORDS)

    df = fetch_daily_price("2330", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))

    assert len(df) == len(_FINMIND_RECORDS)


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

@patch("data.fetchers.price.requests.get")
def test_rows_are_sorted_by_date(mock_get):
    # Feed records in reverse order to confirm sorting
    mock_get.return_value = _mock_response(list(reversed(_FINMIND_RECORDS)))

    df = fetch_daily_price("2330", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))

    dates = list(df["date"])
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# Empty API response raises ValueError
# ---------------------------------------------------------------------------

@patch("data.fetchers.price.requests.get")
def test_empty_api_response_raises_value_error(mock_get):
    mock_get.return_value = _mock_response([])

    with pytest.raises(ValueError, match="No price data returned"):
        fetch_daily_price("9999", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))


# ---------------------------------------------------------------------------
# HTTP error propagates
# ---------------------------------------------------------------------------

@patch("data.fetchers.price.requests.get")
def test_http_error_propagates(mock_get):
    mock = MagicMock()
    mock.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
    mock_get.return_value = mock

    with pytest.raises(requests.HTTPError):
        fetch_daily_price("2330", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))


# ---------------------------------------------------------------------------
# Invalid rows are dropped (schema validation inside fetcher)
# ---------------------------------------------------------------------------

@patch("data.fetchers.price.requests.get")
def test_invalid_rows_are_dropped(mock_get):
    bad_records = _FINMIND_RECORDS + [
        {
            "stock_id": "2330",
            "date": "2024-01-04",
            "open": "560.0",
            "max": "550.0",   # high < low — will fail OHLC check
            "min": "565.0",
            "close": "558.0",
            "Trading_Volume": "1000000",
        }
    ]
    mock_get.return_value = _mock_response(bad_records)

    df = fetch_daily_price("2330", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))

    # Only the 2 valid rows should survive
    assert len(df) == 2
