from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator


class DailyPrice(BaseModel):
    """Daily OHLCV price record for a Taiwan stock."""

    stock_id: str
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int  # shares traded

    @field_validator("stock_id")
    @classmethod
    def stock_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("stock_id must not be empty")
        return v

    @field_validator("open", "high", "low", "close")
    @classmethod
    def price_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("price must be positive")
        return v

    @field_validator("volume")
    @classmethod
    def volume_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("volume must be non-negative")
        return v

    @model_validator(mode="after")
    def ohlc_consistency(self) -> "DailyPrice":
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if not (self.low <= self.open <= self.high):
            raise ValueError("open must be between low and high")
        if not (self.low <= self.close <= self.high):
            raise ValueError("close must be between low and high")
        return self

    model_config = {"frozen": True}


class QuarterlyFundamentals(BaseModel):
    """Quarterly fundamental record for a Taiwan stock.

    Core EPS fields
    ---------------
    report_period : Quarter-end date the figures apply to (e.g. 2024-03-31 = Q1).
    eps           : Basic earnings per share for the quarter (每股盈餘).

    Optional fields
    ---------------
    release_date  : Date the report was officially published. May differ from
                    report_period by 1–3 months. Use this for point-in-time
                    backtesting to avoid lookahead bias.
    diluted_eps   : Diluted EPS when available (稀釋每股盈餘).

    Extension placeholders (Phase 3+)
    ----------------------------------
    revenue       : Quarterly revenue (TWD, thousands).
    pe_ratio      : Price-to-earnings ratio at release_date.
    pb_ratio      : Price-to-book ratio at release_date.
    yoy_eps_growth: Year-over-year EPS growth rate (decimal, e.g. 0.15 = +15%).
    """

    stock_id: str
    report_period: date
    eps: float

    # — Optional enrichment fields ------------------------------------------
    release_date: Optional[date] = None
    diluted_eps: Optional[float] = None

    # — Extension placeholders (populate in Phase 3) ------------------------
    revenue: Optional[float] = None        # TWD thousands
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    yoy_eps_growth: Optional[float] = None  # decimal

    @field_validator("stock_id")
    @classmethod
    def stock_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("stock_id must not be empty")
        return v

    @field_validator("release_date")
    @classmethod
    def release_date_not_before_report(
        cls, v: Optional[date], info: object
    ) -> Optional[date]:
        # Guard against data entry errors — release cannot precede quarter end
        report = getattr(info, "data", {}).get("report_period")
        if v is not None and report is not None and v < report:
            raise ValueError(
                f"release_date ({v}) cannot be before report_period ({report})"
            )
        return v

    model_config = {"frozen": True}


class MarginData(BaseModel):
    """Daily margin financing and short-sale record for a Taiwan stock.

    Primary strategy fields
    -----------------------
    margin_purchase_balance : Outstanding margin long positions (shares) — 融資餘額
    short_sale_balance      : Outstanding margin short positions (shares) — 融券餘額

    Flow fields (today's activity)
    -------------------------------
    margin_purchase_buy     : Shares bought on margin today — 融資買入
    margin_purchase_sell    : Margin long positions closed today — 融資賣出
    short_sale_buy          : Short positions covered today — 融券買入
    short_sale_sell         : New short positions opened today — 融券賣出

    Reference fields
    ----------------
    margin_purchase_limit   : Maximum allowed margin long balance
    short_sale_limit        : Maximum allowed short balance
    """

    stock_id: str
    date: date

    # — Primary balance fields (required) ------------------------------------
    margin_purchase_balance: int        # 融資餘額
    short_sale_balance: int             # 融券餘額

    # — Daily flow fields (optional: may be absent for some data sources) ----
    margin_purchase_buy: Optional[int] = None   # 融資買入
    margin_purchase_sell: Optional[int] = None  # 融資賣出
    short_sale_buy: Optional[int] = None        # 融券買入
    short_sale_sell: Optional[int] = None       # 融券賣出

    # — Limit / capacity fields (optional) -----------------------------------
    margin_purchase_limit: Optional[int] = None
    short_sale_limit: Optional[int] = None

    @field_validator("stock_id")
    @classmethod
    def stock_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("stock_id must not be empty")
        return v

    @field_validator(
        "margin_purchase_balance", "short_sale_balance",
        "margin_purchase_buy", "margin_purchase_sell",
        "short_sale_buy", "short_sale_sell",
        "margin_purchase_limit", "short_sale_limit",
        mode="before",
    )
    @classmethod
    def non_negative_int(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("margin fields must be non-negative")
        return v

    model_config = {"frozen": True}
