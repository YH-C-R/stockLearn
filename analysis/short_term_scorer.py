from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

from data.single_stock_loader import StockData


class TimingSignal(str, Enum):
    GOOD_ENTRY = "GOOD_ENTRY"
    WAIT = "WAIT"
    AVOID = "AVOID"


_GOOD_ENTRY_THRESHOLD = 0.7
_WAIT_THRESHOLD = 0.4

_W_PRICE = 0.30
_W_VOLUME = 0.40
_W_MARGIN = 0.30

_VOLUME_SPIKE_RATIO = 1.5
_MA20_WINDOW = 20
_MA60_WINDOW = 60


@dataclass
class ShortTermScoreResult:
    stock_id: str
    short_term_score: float
    timing_signal: TimingSignal
    price_score: float
    volume_score: float
    margin_score: float
    key_reasons: list[str]
    ma20: Optional[float]
    ma60: Optional[float]


def score_short_term(data: StockData) -> ShortTermScoreResult:
    daily = data.daily

    current_price = _latest(daily, "close")
    ma20 = _moving_average(daily, "close", _MA20_WINDOW)
    ma60 = _moving_average(daily, "close", _MA60_WINDOW)
    recent_high = _recent_high(daily, "close", _MA20_WINDOW)
    current_volume = _latest(daily, "volume")
    avg_volume = _moving_average(daily, "volume", _MA20_WINDOW)
    margin_ratio = _margin_ratio(daily)

    price_score = _score_price(current_price, ma20, recent_high)
    volume_score = _score_volume(current_volume, avg_volume)
    margin_score = _score_margin(margin_ratio)

    final = round(
        price_score * _W_PRICE
        + volume_score * _W_VOLUME
        + margin_score * _W_MARGIN,
        4,
    )

    signal = _classify(final)

    reasons = _build_reasons(
        price_score=price_score,
        volume_score=volume_score,
        margin_score=margin_score,
        current_price=current_price,
        ma20=ma20,
        ma60=ma60,
        current_volume=current_volume,
        avg_volume=avg_volume,
        margin_ratio=margin_ratio,
    )

    return ShortTermScoreResult(
        stock_id=data.stock_id,
        short_term_score=final,
        timing_signal=signal,
        price_score=price_score,
        volume_score=volume_score,
        margin_score=margin_score,
        key_reasons=reasons,
        ma20=ma20,
        ma60=ma60,
    )


def _score_price(
    current_price: Optional[float],
    ma20: Optional[float],
    recent_high: Optional[float],
) -> float:
    if current_price is None or ma20 is None or ma20 <= 0:
        return 0.5

    if recent_high is not None and current_price > recent_high:
        return 1.0

    ratio = current_price / ma20
    score = (ratio - 0.9) / 0.2
    return round(min(max(score, 0.0), 1.0), 4)


def _score_volume(
    current_volume: Optional[float],
    avg_volume: Optional[float],
) -> float:
    if current_volume is None or avg_volume is None or avg_volume <= 0:
        return 0.5

    ratio = current_volume / avg_volume
    if ratio >= _VOLUME_SPIKE_RATIO:
        return 1.0
    if ratio >= 1.0:
        return 0.75
    return 0.25


def _score_margin(margin_ratio: Optional[float]) -> float:
    if margin_ratio is None:
        return 0.5
    if margin_ratio < -0.1:
        return 1.0
    if margin_ratio < -0.02:
        return 0.75
    if margin_ratio < 0.02:
        return 0.5
    if margin_ratio < 0.1:
        return 0.3
    return 0.0


def _latest(daily: pd.DataFrame, col: str) -> Optional[float]:
    if col not in daily.columns or daily.empty:
        return None
    series = daily[col].dropna()
    if series.empty:
        return None
    return float(series.iloc[-1])


def _moving_average(
    daily: pd.DataFrame,
    col: str,
    window: int,
) -> Optional[float]:
    if col not in daily.columns or daily.empty:
        return None
    series = daily[col].dropna()
    if len(series) < window:
        return None
    return float(series.rolling(window).mean().iloc[-1])


def _recent_high(
    daily: pd.DataFrame,
    col: str,
    window: int,
) -> Optional[float]:
    if col not in daily.columns or daily.empty:
        return None
    series = daily[col].dropna()
    if len(series) < window:
        return None
    return float(series.iloc[-window:].max())


def _margin_ratio(daily: pd.DataFrame) -> Optional[float]:
    col = "margin_purchase_balance"
    if col not in daily.columns or daily.empty:
        return None

    series = daily[col].dropna()
    if len(series) < 10:
        return None

    recent = series.iloc[-5:].mean()
    prior = series.iloc[-10:-5].mean()

    if prior == 0:
        return None

    return (recent - prior) / prior


def _classify(score: float) -> TimingSignal:
    if score >= _GOOD_ENTRY_THRESHOLD:
        return TimingSignal.GOOD_ENTRY
    if score >= _WAIT_THRESHOLD:
        return TimingSignal.WAIT
    return TimingSignal.AVOID


def _build_reasons(
    price_score: float,
    volume_score: float,
    margin_score: float,
    current_price: Optional[float],
    ma20: Optional[float],
    ma60: Optional[float],
    current_volume: Optional[float],
    avg_volume: Optional[float],
    margin_ratio: Optional[float],
) -> list[str]:
    reasons: list[str] = []

    if current_price is None or ma20 is None:
        reasons.append("price data unavailable")
    elif price_score >= 0.7:
        reasons.append("price in uptrend / breakout")
    elif price_score <= 0.3:
        reasons.append("price below trend (weak)")
    else:
        reasons.append("price near MA20")

    if ma20 is not None and ma60 is not None:
        if ma20 > ma60:
            reasons.append("short-term trend above mid-term trend")
        elif ma20 < ma60:
            reasons.append("short-term trend below mid-term trend")

    if current_volume is None or avg_volume is None:
        reasons.append("volume data unavailable")
    elif volume_score == 1.0:
        reasons.append("volume spike (strong momentum)")
    elif volume_score == 0.75:
        reasons.append("volume above average")
    else:
        reasons.append("low volume (weak confirmation)")

    if margin_ratio is None:
        reasons.append("margin data unavailable")
    elif margin_score >= 0.75:
        reasons.append("margin decreasing (bullish)")
    elif margin_score <= 0.3:
        reasons.append("margin increasing (bearish)")
    else:
        reasons.append("margin neutral")

    return reasons[:3]


def print_short_term_score(result: ShortTermScoreResult) -> None:
    div = "─" * 52

    def row(label: str, value: object) -> None:
        print(f"  {label:<24}: {value}")

    def frow(label: str, value: Optional[float]) -> None:
        if value is None:
            print(f"  {label:<24}: N/A")
        else:
            print(f"  {label:<24}: {value:.4f}")

    print(f"\n{div}")
    print(f"  {result.stock_id}  —  Short-Term Score")
    print(div)

    row("Timing signal", result.timing_signal.value)
    frow("Short-term score", result.short_term_score)

    print(f"  {'─'*48}")

    frow("Price score", result.price_score)
    frow("Volume score", result.volume_score)
    frow("Margin score", result.margin_score)
    frow("MA20", result.ma20)
    frow("MA60", result.ma60)

    print(f"  {'─'*48}")

    if result.key_reasons:
        print(f"  {'Reasons':<24}:")
        for r in result.key_reasons:
            print(f"    • {r}")

    print(f"{div}\n")