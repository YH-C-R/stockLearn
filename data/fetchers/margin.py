import logging
from datetime import date
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
_DATASET = "TaiwanStockMarginPurchaseShortSale"

# FinMind response column → normalised field name
_COLUMN_MAP = {
    "stock_id":                         "stock_id",
    "date":                             "date",
    "MarginPurchaseBuy":                "margin_purchase_buy",       # 融資買入 (shares)
    "MarginPurchaseSell":               "margin_purchase_sell",      # 融資賣出 (shares)
    "MarginPurchaseCashRepayment":      "margin_purchase_cash_repayment",  # 融資現金償還
    "MarginPurchaseYesterdayBalance":   "margin_purchase_prev_balance",    # 前日融資餘額
    "MarginPurchaseTodayBalance":       "margin_purchase_balance",   # 融資餘額 (shares)
    "MarginPurchaseLimit":              "margin_purchase_limit",     # 融資限額
    "ShortSaleBuy":                     "short_sale_buy",            # 融券買入 (shares)
    "ShortSaleSell":                    "short_sale_sell",           # 融券賣出 (shares)
    "ShortSaleCashRepayment":           "short_sale_cash_repayment", # 融券現金償還
    "ShortSaleYesterdayBalance":        "short_sale_prev_balance",   # 前日融券餘額
    "ShortSaleTodayBalance":            "short_sale_balance",        # 融券餘額 (shares)
    "ShortSaleLimit":                   "short_sale_limit",          # 融券限額
}

# Columns expected to hold integer values after normalisation
_INT_COLUMNS = [c for c in _COLUMN_MAP.values() if c not in ("stock_id", "date")]


def fetch_margin_data(
    stock_id: str,
    start_date: date,
    end_date: Optional[date] = None,
    token: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch daily margin financing and short-sale data from FinMind.

    Parameters
    ----------
    stock_id   : Taiwan stock ticker (e.g. "2330").
    start_date : Inclusive start date.
    end_date   : Inclusive end date. Defaults to today.
    token      : FinMind API token. Unauthenticated requests are rate-limited.

    Returns
    -------
    DataFrame with normalised columns (see _COLUMN_MAP for the full list).
    Key columns for strategy use:
      - margin_purchase_balance : Outstanding margin long positions (shares).
      - short_sale_balance      : Outstanding margin short positions (shares).

    Raises
    ------
    requests.HTTPError : On non-2xx HTTP responses.
    ValueError         : If the API returns no data for the given parameters.
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
            f"No margin data returned for {stock_id} "
            f"({start_date} – {end_date}). "
            "Check the stock_id and date range."
        )

    df = pd.DataFrame(records)
    df = _normalize(df, stock_id)
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(df: pd.DataFrame, stock_id: str) -> pd.DataFrame:
    """Select, rename, cast, and sort the raw FinMind response."""
    missing = set(_COLUMN_MAP.keys()) - set(df.columns)
    if missing:
        raise ValueError(f"FinMind margin response missing expected columns: {missing}")

    df = df[list(_COLUMN_MAP.keys())].rename(columns=_COLUMN_MAP)
    df["date"]     = pd.to_datetime(df["date"]).dt.date
    df["stock_id"] = stock_id

    for col in _INT_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    return df.sort_values("date")
