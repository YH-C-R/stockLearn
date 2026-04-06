from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from data.storage.schema import DailyPrice


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_DATA = {
    "stock_id": "2330",
    "date": date(2024, 1, 2),
    "open": Decimal("560.0"),
    "high": Decimal("575.0"),
    "low": Decimal("558.0"),
    "close": Decimal("570.0"),
    "volume": 25_000_000,
}


# ---------------------------------------------------------------------------
# Valid record
# ---------------------------------------------------------------------------

def test_valid_record_passes():
    record = DailyPrice(**VALID_DATA)
    assert record.stock_id == "2330"
    assert record.close == Decimal("570.0")
    assert record.volume == 25_000_000


def test_record_is_immutable():
    record = DailyPrice(**VALID_DATA)
    with pytest.raises(ValidationError):
        record.close = Decimal("999.0")


# ---------------------------------------------------------------------------
# stock_id validation
# ---------------------------------------------------------------------------

def test_empty_stock_id_fails():
    with pytest.raises(ValidationError, match="stock_id must not be empty"):
        DailyPrice(**{**VALID_DATA, "stock_id": "   "})


# ---------------------------------------------------------------------------
# Price validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
def test_zero_price_fails(field):
    with pytest.raises(ValidationError, match="price must be positive"):
        DailyPrice(**{**VALID_DATA, field: Decimal("0")})


@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
def test_negative_price_fails(field):
    with pytest.raises(ValidationError, match="price must be positive"):
        DailyPrice(**{**VALID_DATA, field: Decimal("-1.0")})


# ---------------------------------------------------------------------------
# Volume validation
# ---------------------------------------------------------------------------

def test_negative_volume_fails():
    with pytest.raises(ValidationError, match="volume must be non-negative"):
        DailyPrice(**{**VALID_DATA, "volume": -1})


def test_zero_volume_passes():
    # Zero volume is valid (e.g. trading halt with no transactions)
    record = DailyPrice(**{**VALID_DATA, "volume": 0})
    assert record.volume == 0


# ---------------------------------------------------------------------------
# OHLC consistency
# ---------------------------------------------------------------------------

def test_high_less_than_low_fails():
    with pytest.raises(ValidationError, match="high must be >= low"):
        DailyPrice(**{**VALID_DATA, "high": Decimal("550.0"), "low": Decimal("560.0")})


def test_open_above_high_fails():
    with pytest.raises(ValidationError, match="open must be between low and high"):
        DailyPrice(**{**VALID_DATA, "open": Decimal("580.0")})


def test_close_below_low_fails():
    with pytest.raises(ValidationError, match="close must be between low and high"):
        DailyPrice(**{**VALID_DATA, "close": Decimal("550.0")})
