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


class DailyFundamentals(BaseModel):
    """Placeholder for per-share fundamental data (Phase 2)."""

    stock_id: str
    date: date
    eps: Optional[Decimal] = None
    pe_ratio: Optional[Decimal] = None
    pb_ratio: Optional[Decimal] = None

    model_config = {"frozen": True}


class MarginData(BaseModel):
    """Placeholder for margin trading data (Phase 2)."""

    stock_id: str
    date: date
    margin_buy: Optional[int] = None    # 融資買入 (shares)
    margin_sell: Optional[int] = None   # 融資賣出 (shares)
    short_buy: Optional[int] = None     # 融券買入 (shares)
    short_sell: Optional[int] = None    # 融券賣出 (shares)

    model_config = {"frozen": True}
