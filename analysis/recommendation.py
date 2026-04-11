"""Turn a combined score into a human-readable recommendation.

Accepts the output of the scoring and loader layers and produces a
``RecommendationResult`` suitable for printing or logging.

Recommendation tiers (long-term investing focus)
-------------------------------------------------
STRONG BUY : Strong signal across multiple strategies.  Enter now.
WATCH      : Good signal but no active breakout.  Enter on pullback.
WAIT       : Weak signal; stock may be fundamentally acceptable but
             timing is not yet right.  Monitor for re-entry conditions.
AVOID      : No meaningful signal or insufficient data.

Usage
-----
    from data.single_stock_loader import load_stock
    from analysis.single_stock_analysis import analyze_stock
    from analysis.single_stock_scoring import score_stock
    from analysis.recommendation import recommend, print_recommendation

    data     = load_stock("2330", start, end, token=TOKEN)
    analysis = analyze_stock(data)
    scored   = score_stock(analysis)
    rec      = recommend(scored, data)
    print_recommendation(rec)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import pandas as pd

from analysis.single_stock_scoring import StockScoreResult
from data.single_stock_loader import StockData


# ---------------------------------------------------------------------------
# Recommendation tiers
# ---------------------------------------------------------------------------

class Recommendation(str, Enum):
    STRONG_BUY = "STRONG BUY"
    WATCH      = "WATCH"
    WAIT       = "WAIT"
    AVOID      = "AVOID"


# Score thresholds — adjust here only
_STRONG_BUY_THRESHOLD = 0.6
_WATCH_THRESHOLD      = 0.3
_WAIT_THRESHOLD       = 0.1   # below this → AVOID


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class RecommendationResult:
    """Full recommendation output for a single stock.

    Attributes
    ----------
    stock_id        : Stock ticker.
    as_of_date      : Date of the latest signal used.
    recommendation  : STRONG BUY / WATCH / WAIT / AVOID.
    reasons         : Short human-readable signals driving the recommendation.
    final_score     : Combined weighted score.
    pv_score        : Price-volume strategy score.
    mt_score        : Margin-trend strategy score.
    dd_score        : Davis-double strategy score.
    current_price   : Latest closing price.
    ma20            : 20-day moving average (None if insufficient history).
    ma50            : 50-day moving average (None if insufficient history).
    pe              : Latest trailing PE ratio (None if EPS unavailable).
    eps             : Latest forward-filled EPS (None if unavailable).
    eps_trend       : "improving", "declining", "flat", or "unknown".
    suggested_entry : Suggested entry price (always provided when price data exists).
    entry_basis     : Why that entry price was chosen.
    """
    stock_id:        str
    as_of_date:      object            # date or None
    recommendation:  Recommendation
    reasons:         list[str]
    final_score:     float
    pv_score:        float
    mt_score:        float
    dd_score:        float
    current_price:   Optional[float]
    ma20:            Optional[float]
    ma50:            Optional[float]
    pe:              Optional[float]
    eps:             Optional[float]
    eps_trend:       str
    suggested_entry: Optional[float]
    entry_basis:     str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def recommend(
    scored: StockScoreResult,
    data:   StockData,
) -> RecommendationResult:
    """Produce a recommendation from scoring and market data.

    Parameters
    ----------
    scored : Output of ``score_stock()``.
    data   : Output of ``load_stock()``, used for price / PE / EPS context.

    Returns
    -------
    RecommendationResult.  Works even when signals or market data are absent;
    missing fields are None and recommendation defaults to AVOID.
    """
    daily = data.daily

    # ── Latest market data ────────────────────────────────────────────────────
    current_price = _latest(daily, "close")
    pe            = _latest(daily, "pe")
    eps           = _latest(daily, "eps")
    ma20          = _moving_average(daily["close"], 20) if not daily.empty else None
    ma50          = _moving_average(daily["close"], 50) if not daily.empty else None
    eps_trend     = _eps_trend(daily)

    # ── Score breakdown ───────────────────────────────────────────────────────
    snap = scored.snapshot
    if snap is None:
        final_score = 0.0
        pv_score    = 0.0
        mt_score    = 0.0
        dd_score    = 0.0
        as_of_date  = None
    else:
        final_score = snap.final_score
        pv_score    = snap.pv_score
        mt_score    = snap.mt_score
        dd_score    = snap.dd_score
        as_of_date  = snap.date

    # ── Classify + build reason list ──────────────────────────────────────────
    rec     = _classify(final_score)
    reasons = _build_reasons(
        pv_score  = pv_score,
        mt_score  = mt_score,
        dd_score  = dd_score,
        eps_trend = eps_trend,
        pe        = pe,
        snap      = snap,
    )

    # ── Suggested entry ───────────────────────────────────────────────────────
    suggested_entry, entry_basis = _entry_price(
        rec           = rec,
        pv_score      = pv_score,
        current_price = current_price,
        ma20          = ma20,
        ma50          = ma50,
    )

    return RecommendationResult(
        stock_id        = data.stock_id,
        as_of_date      = as_of_date,
        recommendation  = rec,
        reasons         = reasons,
        final_score     = round(final_score, 4),
        pv_score        = round(pv_score, 4),
        mt_score        = round(mt_score, 4),
        dd_score        = round(dd_score, 4),
        current_price   = current_price,
        ma20            = ma20,
        ma50            = ma50,
        pe              = pe,
        eps             = eps,
        eps_trend       = eps_trend,
        suggested_entry = suggested_entry,
        entry_basis     = entry_basis,
    )


def print_recommendation(rec: RecommendationResult) -> None:
    """Print a formatted recommendation summary to stdout."""
    _divider = "─" * 52

    def row(label: str, value: object, suffix: str = "") -> None:
        val = "N/A" if value is None else f"{value}{suffix}"
        print(f"  {label:<22}: {val}")

    def frow(label: str, value: Optional[float], fmt: str = ".2f", suffix: str = "") -> None:
        val = "N/A" if value is None else f"{value:{fmt}}{suffix}"
        print(f"  {label:<22}: {val}")

    print(f"\n{_divider}")
    print(f"  {rec.stock_id}  —  {rec.recommendation.value}")
    print(_divider)

    row("As of date",     rec.as_of_date)
    frow("Current price", rec.current_price, suffix=" TWD")
    frow("MA20",          rec.ma20,          suffix=" TWD")
    frow("MA50",          rec.ma50,          suffix=" TWD")
    frow("PE",            rec.pe)
    frow("EPS (latest)",  rec.eps,           suffix=" TWD")
    row("EPS trend",      rec.eps_trend)

    print(f"  {'─'*48}")

    frow("PV score",    rec.pv_score,    fmt=".4f")
    frow("Margin score", rec.mt_score,   fmt=".4f")
    frow("Davis score",  rec.dd_score,   fmt=".4f")
    frow("Final score",  rec.final_score, fmt=".4f")

    print(f"  {'─'*48}")

    print(f"  {'Recommendation':<22}: {rec.recommendation.value}")
    if rec.reasons:
        print(f"  {'Reasons':<22}:")
        for r in rec.reasons:
            print(f"    • {r}")
    frow("Suggested entry", rec.suggested_entry, suffix=" TWD")
    row("Entry basis",      rec.entry_basis)

    print(f"{_divider}\n")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _classify(final_score: float) -> Recommendation:
    if final_score >= _STRONG_BUY_THRESHOLD:
        return Recommendation.STRONG_BUY
    if final_score >= _WATCH_THRESHOLD:
        return Recommendation.WATCH
    if final_score >= _WAIT_THRESHOLD:
        return Recommendation.WAIT
    return Recommendation.AVOID


def _build_reasons(
    pv_score:  float,
    mt_score:  float,
    dd_score:  float,
    eps_trend: str,
    pe:        Optional[float],
    snap:      object,
) -> list[str]:
    """Compile short signal-state descriptions for the current snapshot."""
    reasons: list[str] = []

    if snap is None:
        reasons.append("no active signals")
        return reasons

    # Price-volume
    if pv_score >= 0.8:
        reasons.append("breakout confirmed with volume")
    elif pv_score >= 0.4:
        reasons.append("breakout without volume confirmation")
    else:
        reasons.append("breakout inactive")

    # Margin trend
    if mt_score > 0:
        reasons.append("margin trend positive")
    elif mt_score < 0:
        reasons.append("margin trend negative")
    else:
        reasons.append("margin trend neutral")

    # Davis Double
    if dd_score > 0:
        reasons.append(f"Davis Double active (score {dd_score:.2f})")
    else:
        reasons.append("no active Davis signal")

    # EPS trend
    if eps_trend == "improving":
        reasons.append("EPS improving")
    elif eps_trend == "declining":
        reasons.append("EPS declining")

    # Valuation flag (soft, not blocking)
    if pe is not None and pe > 30:
        reasons.append("valuation elevated (PE > 30)")

    return reasons


def _entry_price(
    rec:           Recommendation,
    pv_score:      float,
    current_price: Optional[float],
    ma20:          Optional[float],
    ma50:          Optional[float],
) -> tuple[Optional[float], str]:
    """Determine a suggested entry price for all recommendation tiers.

    STRONG BUY / WATCH : enter at breakout price or wait for MA pullback.
    WAIT               : provide an MA reference even though timing is off.
    AVOID              : no entry suggested.
    """
    if current_price is None:
        return None, "no price data"

    if rec == Recommendation.AVOID:
        return None, "no entry — score too low"

    # Active breakout confirmed → enter at market
    if pv_score > 0:
        return round(current_price, 2), "breakout confirmed — enter at market"

    # No breakout: suggest nearest MA below current price as pullback target
    if ma20 is not None and ma20 < current_price:
        label = "watch entry" if rec == Recommendation.WAIT else "wait for pullback"
        return round(ma20, 2), f"{label} near MA20"

    if ma50 is not None and ma50 < current_price:
        label = "watch entry" if rec == Recommendation.WAIT else "wait for pullback"
        return round(ma50, 2), f"{label} near MA50"

    # MAs above price or unavailable — use current price as reference
    return round(current_price, 2), "reference price (MA above or unavailable)"


def _moving_average(close: pd.Series, window: int) -> Optional[float]:
    """Return the latest N-day SMA, or None if insufficient history."""
    if len(close) < window:
        return None
    ma = close.rolling(window).mean().iloc[-1]
    return round(float(ma), 2) if pd.notna(ma) else None


def _latest(daily: pd.DataFrame, col: str) -> Optional[float]:
    """Return the last non-NaN value of a column, or None."""
    if col not in daily.columns or daily.empty:
        return None
    series = daily[col].dropna()
    if series.empty:
        return None
    return round(float(series.iloc[-1]), 2)


def _eps_trend(daily: pd.DataFrame) -> str:
    """Classify EPS trend from the last two distinct quarterly values."""
    if "eps" not in daily.columns or daily.empty:
        return "unknown"
    eps_series = daily["eps"].dropna()
    if eps_series.empty:
        return "unknown"
    distinct = eps_series[eps_series.ne(eps_series.shift())].values
    if len(distinct) < 2:
        return "unknown"
    prev, latest = float(distinct[-2]), float(distinct[-1])
    if latest > prev * 1.05:
        return "improving"
    if latest < prev * 0.95:
        return "declining"
    return "flat"
