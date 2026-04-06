from datetime import date
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, field_validator


class SignalDirection(str, Enum):
    """Normalised direction so aggregators can act without parsing signal_name."""
    BULLISH  = "bullish"
    BEARISH  = "bearish"
    NEUTRAL  = "neutral"


class Signal(BaseModel):
    """Common output contract for all strategy modules.

    Every strategy produces a list of Signal objects so that the aggregator
    layer can combine them without knowing anything about their internals.

    Fields
    ------
    stock_id     : Taiwan stock ticker (e.g. "2330").
    date         : The trading date this signal applies to.
    signal_name  : Machine-readable strategy identifier (e.g. "ma_crossover").
    signal_value : Raw numeric output of the strategy (e.g. RSI value, spread).
    score        : Normalised strength in [-1.0, 1.0].
                   -1 = strongest bearish, 0 = neutral, +1 = strongest bullish.
    direction    : Coarse direction derived from score; defaults to NEUTRAL.
    metadata     : Optional dict for strategy-specific extras (e.g. window sizes,
                   component values). Not used in aggregation logic.
    """

    stock_id: str
    date: date
    signal_name: str
    signal_value: float
    score: float
    direction: SignalDirection = SignalDirection.NEUTRAL
    metadata: Optional[dict[str, Any]] = None

    @field_validator("stock_id")
    @classmethod
    def stock_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("stock_id must not be empty")
        return v

    @field_validator("signal_name")
    @classmethod
    def signal_name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("signal_name must not be empty")
        return v

    @field_validator("score")
    @classmethod
    def score_in_range(cls, v: float) -> float:
        if not -1.0 <= v <= 1.0:
            raise ValueError(f"score must be in [-1.0, 1.0], got {v}")
        return v

    model_config = {"frozen": True}


def make_signal(
    stock_id: str,
    date: date,
    signal_name: str,
    signal_value: float,
    score: float,
    metadata: Optional[dict[str, Any]] = None,
) -> Signal:
    """Construct a Signal and infer direction from score.

    Direction rules:
        score > 0   → BULLISH
        score < 0   → BEARISH
        score == 0  → NEUTRAL
    """
    if score > 0:
        direction = SignalDirection.BULLISH
    elif score < 0:
        direction = SignalDirection.BEARISH
    else:
        direction = SignalDirection.NEUTRAL

    return Signal(
        stock_id=stock_id,
        date=date,
        signal_name=signal_name,
        signal_value=signal_value,
        score=score,
        direction=direction,
        metadata=metadata,
    )
