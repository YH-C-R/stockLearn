import logging
from datetime import date
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"

# FinMind provides two complementary EPS datasets:
#   TaiwanStockFinancialStatements — quarterly income statement items including EPS
#   TaiwanStockMonthRevenue        — monthly revenue (leading indicator, released faster)
#
# We fetch TaiwanStockFinancialStatements and filter to EPS-related rows.
_DATASET = "TaiwanStockFinancialStatements"

# The financial statements dataset is "long" format: one row per (stock, date, type).
# We keep only EPS rows; the `type` field identifies the metric.
_EPS_TYPES = {
    "EPS",                    # Basic EPS (每股盈餘)
    "BasicEPS",               # Alternate label used by some filings
    "DilutedEPS",             # Diluted EPS (稀釋每股盈餘)
}

# FinMind response column → normalised field name
_COLUMN_MAP = {
    "stock_id": "stock_id",
    "date":     "report_period",   # quarter end date (e.g. 2024-03-31)
    "type":     "metric",
    "value":    "value",
    "origin_name": "origin_name",  # original Chinese label — kept for traceability
}

_FLOAT_COLUMNS = ["value"]


def fetch_eps_data(
    stock_id: str,
    start_date: date,
    end_date: Optional[date] = None,
    token: Optional[str] = None,
    include_diluted: bool = False,
) -> pd.DataFrame:
    """Fetch quarterly EPS data for a Taiwan stock from FinMind.

    Fetches ``TaiwanStockFinancialStatements`` and returns only EPS rows,
    pivoted to one row per quarter so downstream strategy code can join
    directly against a price or margin DataFrame.

    Parameters
    ----------
    stock_id        : Taiwan stock ticker (e.g. "2330").
    start_date      : Inclusive start of the report_period range.
    end_date        : Inclusive end of the report_period range. Defaults to today.
    token           : FinMind API token. Unauthenticated requests are rate-limited.
    include_diluted : If True, also return a ``diluted_eps`` column when available.

    Returns
    -------
    DataFrame with one row per quarter-end date and columns:
        stock_id, report_period, eps, diluted_eps (optional)

    ``report_period`` is a ``datetime.date`` representing the quarter end
    (e.g. 2024-03-31 for Q1 2024).

    Raises
    ------
    requests.HTTPError : On non-2xx HTTP responses.
    ValueError         : If the API returns no EPS data for the given parameters.
    """
    if end_date is None:
        end_date = date.today()

    params: dict = {
        "dataset":    _DATASET,
        "data_id":    stock_id,
        "start_date": start_date.isoformat(),
        "end_date":   end_date.isoformat(),
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
            f"No financial statement data returned for {stock_id} "
            f"({start_date} – {end_date}). "
            "Check the stock_id and date range."
        )

    df = pd.DataFrame(records)
    df = _normalize(df, stock_id)
    df = _pivot_eps(df, include_diluted)

    if df.empty:
        raise ValueError(
            f"No EPS rows found for {stock_id} ({start_date} – {end_date}). "
            f"Available metric types: {records[0].get('type', 'unknown')!r} …"
        )

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(df: pd.DataFrame, stock_id: str) -> pd.DataFrame:
    """Rename columns, cast types, and filter to EPS-related rows."""
    missing = set(_COLUMN_MAP.keys()) - set(df.columns)
    if missing:
        raise ValueError(
            f"FinMind financial statements response missing expected columns: {missing}"
        )

    df = df[list(_COLUMN_MAP.keys())].rename(columns=_COLUMN_MAP)
    df["report_period"] = pd.to_datetime(df["report_period"]).dt.date
    df["stock_id"]      = stock_id

    for col in _FLOAT_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Keep only EPS-related metrics
    df = df[df["metric"].isin(_EPS_TYPES)].copy()
    return df.sort_values("report_period")


def _pivot_eps(df: pd.DataFrame, include_diluted: bool) -> pd.DataFrame:
    """Pivot long-format EPS rows into one row per quarter.

    Precedence for the ``eps`` column:
        BasicEPS > EPS  (BasicEPS is the more explicit label)
    ``diluted_eps`` maps to DilutedEPS when present.
    """
    if df.empty:
        return df

    rows = []
    for period, group in df.groupby("report_period"):
        stock_id = group["stock_id"].iloc[0]

        metric_map: dict[str, float] = dict(
            zip(group["metric"], group["value"])
        )

        # Basic EPS — prefer "BasicEPS" label, fall back to "EPS"
        eps = metric_map.get("BasicEPS") or metric_map.get("EPS")

        row: dict = {
            "stock_id":      stock_id,
            "report_period": period,
            "eps":           eps,
        }

        if include_diluted:
            row["diluted_eps"] = metric_map.get("DilutedEPS")

        rows.append(row)

    result = pd.DataFrame(rows)

    # Drop quarters where EPS could not be resolved
    result = result.dropna(subset=["eps"])
    result["eps"] = result["eps"].astype(float)

    if include_diluted and "diluted_eps" in result.columns:
        result["diluted_eps"] = pd.to_numeric(result["diluted_eps"], errors="coerce")

    return result.sort_values("report_period")
