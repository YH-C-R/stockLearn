"""Long-term fundamental quality scorer.

Evaluates whether a stock is suitable for long-term holding based on
fundamental trends — not short-term price movement.

Scoring components
------------------
  EPS Trend      (50 %) — consistency and direction of earnings growth
  PE Re-rating   (30 %) — current valuation vs historical average
  Growth Quality (20 %) — revenue YoY growth rate

Classification
--------------
  STRONG_LONG : score >= 0.7
  NEUTRAL     : 0.4 <= score < 0.7
  WEAK        : score < 0.4

Usage
-----
    from data.single_stock_loader import load_stock
    from analysis.long_term_scorer import score_long_term, print_long_term_score

    data   = load_stock("2330", start, end, token=TOKEN)
    result = score_long_term(data)
    print_long_term_score(result)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

from data.single_stock_loader import StockData


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

class LongTermClass(str, Enum):
    STRONG_LONG = "STRONG_LONG"
    NEUTRAL     = "NEUTRAL"
    WEAK        = "WEAK"


_STRONG_LONG_THRESHOLD = 0.7
_NEUTRAL_THRESHOLD     = 0.4


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

_W_EPS    = 0.50
_W_PE     = 0.30
_W_GROWTH = 0.20


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class LongTermScoreResult:
    """Output of ``score_long_term()``.

    Attributes
    ----------
    stock_id         : Stock ticker.
    long_term_score  : Weighted composite score in [0, 1].
    classification   : STRONG_LONG / NEUTRAL / WEAK.
    key_reasons      : Up to 3 plain-language driver sentences.
    eps_score        : Component score for EPS trend (0–1).
    pe_score         : Component score for PE re-rating (0–1).
    growth_score     : Component score for revenue growth (0–1).
    eps_quarters     : List of distinct quarterly EPS values used (oldest→latest).
    current_pe       : Latest PE ratio (None if unavailable).
    avg_pe           : Historical average PE over the data window (None if unavailable).
    revenue_growth   : Revenue YoY growth passed in by caller (None if not provided).
    """
    stock_id:        str
    long_term_score: float
    classification:  LongTermClass
    key_reasons:     list[str]
    eps_score:       float
    pe_score:        float
    growth_score:    float
    eps_quarters:    list[float]
    current_pe:      Optional[float]
    avg_pe:          Optional[float]
    revenue_growth:  Optional[float]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_long_term(
    data:            StockData,
    revenue_growth:  Optional[float] = None,   # YoY % e.g. 15.0 means +15 %
    roe:             Optional[float] = None,    # reserved, not yet used in scoring
    max_eps_quarters: int = 8,
) -> LongTermScoreResult:
    """Score a stock for long-term holding quality.

    Parameters
    ----------
    data             : Output of ``load_stock()``.
    revenue_growth   : Latest revenue YoY growth in percent (optional).
                       When None the growth component is scored as neutral (0.5).
    roe              : Return on equity in percent (optional, reserved for future use).
    max_eps_quarters : Number of recent quarterly EPS values to consider (default 8).

    Returns
    -------
    LongTermScoreResult with score, classification, and key reasons.
    """
    daily = data.daily

    # ── 1. Extract quarterly EPS ───────────────────────────────────────────────
    eps_quarters = _extract_quarterly_eps(daily, max_eps_quarters)

    # ── 2. Extract PE series ───────────────────────────────────────────────────
    current_pe, avg_pe = _pe_stats(daily)

    # ── 3. Score each component ────────────────────────────────────────────────
    eps_score    = _score_eps_trend(eps_quarters)
    pe_score     = _score_pe_rerating(current_pe, avg_pe)
    growth_score = _score_growth(revenue_growth)

    # ── 4. Weighted sum ────────────────────────────────────────────────────────
    final = round(
        eps_score * _W_EPS + pe_score * _W_PE + growth_score * _W_GROWTH, 4
    )

    # ── 5. Classify ───────────────────────────────────────────────────────────
    classification = _classify(final)

    # ── 6. Key reasons (max 3) ────────────────────────────────────────────────
    reasons = _build_reasons(
        eps_quarters   = eps_quarters,
        eps_score      = eps_score,
        pe_score       = pe_score,
        growth_score   = growth_score,
        current_pe     = current_pe,
        avg_pe         = avg_pe,
        revenue_growth = revenue_growth,
    )

    return LongTermScoreResult(
        stock_id        = data.stock_id,
        long_term_score = final,
        classification  = classification,
        key_reasons     = reasons,
        eps_score       = round(eps_score, 4),
        pe_score        = round(pe_score, 4),
        growth_score    = round(growth_score, 4),
        eps_quarters    = eps_quarters,
        current_pe      = current_pe,
        avg_pe          = avg_pe,
        revenue_growth  = revenue_growth,
    )


def print_long_term_score(result: LongTermScoreResult) -> None:
    """Print a formatted long-term score report to stdout."""
    div = "─" * 52

    def row(label: str, value: object, suffix: str = "") -> None:
        val = "N/A" if value is None else f"{value}{suffix}"
        print(f"  {label:<24}: {val}")

    def frow(label: str, value: Optional[float], fmt: str = ".2f", suffix: str = "") -> None:
        val = "N/A" if value is None else f"{value:{fmt}}{suffix}"
        print(f"  {label:<24}: {val}")

    print(f"\n{div}")
    print(f"  {result.stock_id}  —  Long-Term Score")
    print(div)

    frow("Long-term score",   result.long_term_score, fmt=".4f")
    row("Classification",     result.classification.value)

    print(f"  {'─'*48}")

    frow("EPS score   (50%)", result.eps_score,    fmt=".4f")
    frow("PE score    (30%)", result.pe_score,     fmt=".4f")
    frow("Growth score(20%)", result.growth_score, fmt=".4f")

    print(f"  {'─'*48}")

    frow("Current PE",        result.current_pe)
    frow("Historical avg PE", result.avg_pe)
    if result.revenue_growth is not None:
        frow("Revenue YoY",   result.revenue_growth, suffix="%")
    else:
        row("Revenue YoY",    None)

    if result.eps_quarters:
        q_str = "  →  ".join(f"{v:.2f}" for v in result.eps_quarters[-4:])
        print(f"  {'Last 4 qtrs EPS':<24}: {q_str}")

    print(f"  {'─'*48}")

    if result.key_reasons:
        print(f"  {'Key reasons':<24}:")
        for r in result.key_reasons:
            print(f"    • {r}")

    print(f"{div}\n")


# ---------------------------------------------------------------------------
# Component scorers
# ---------------------------------------------------------------------------

def _score_eps_trend(eps_quarters: list[float]) -> float:
    """Score EPS trend on a 0–1 scale.

    Uses year-over-year comparison (Q[n] vs Q[n-4]) to remove seasonality.
    Falls back to quarter-over-quarter slope when fewer than 5 quarters exist.
    Returns 0.5 (neutral) when no EPS data is available.
    """
    n = len(eps_quarters)

    if n == 0:
        return 0.5   # neutral — no data

    # YoY comparison (requires at least 5 quarters: 4 for prior year + 1 current)
    if n >= 5:
        yoy_changes = []
        for i in range(4, n):
            prev = eps_quarters[i - 4]
            curr = eps_quarters[i]
            if prev == 0:
                continue
            yoy_changes.append((curr - prev) / abs(prev))

        if yoy_changes:
            positive = sum(1 for c in yoy_changes if c > 0.02)   # >2% threshold
            negative = sum(1 for c in yoy_changes if c < -0.02)
            total    = len(yoy_changes)
            # Blend win-rate and average growth magnitude
            win_rate = positive / total
            avg_growth = float(np.mean(yoy_changes))
            # Map avg_growth: -50% → 0.0, 0% → 0.5, +50% → 1.0
            growth_component = min(max(avg_growth / 0.5 * 0.5 + 0.5, 0.0), 1.0)
            return round(win_rate * 0.6 + growth_component * 0.4, 4)

    # Fallback: linear slope on available quarters
    if n >= 2:
        x = np.arange(n, dtype=float)
        slope, _ = np.polyfit(x, eps_quarters, 1)
        mean_eps  = abs(np.mean(eps_quarters)) or 1.0
        # Normalise slope relative to mean EPS magnitude
        normalised = slope / mean_eps
        # Map: -0.5 → 0.0, 0 → 0.5, +0.5 → 1.0
        return round(min(max(normalised / 0.5 * 0.5 + 0.5, 0.0), 1.0), 4)

    return 0.5   # single quarter — neutral


def _score_pe_rerating(current_pe: Optional[float], avg_pe: Optional[float]) -> float:
    """Score PE re-rating on a 0–1 scale.

    current_pe > avg_pe → market paying a premium → positive (>0.5)
    current_pe < avg_pe → market discount → negative (<0.5)
    Returns 0.5 when either value is unavailable.
    """
    if current_pe is None or avg_pe is None or avg_pe <= 0:
        return 0.5
    
    if current_pe > 100:
        return 0.3
    
    ratio = current_pe / avg_pe
    if ratio <= 1.5:
        score = (ratio - 0.5) / 1.0
    else:
        # ⭐ 過熱懲罰
        excess = ratio - 1.5
        penalty = min(excess * 0.5, 0.5)
        score = 1.0 - penalty
    return round(min(max(score, 0.0), 1.0), 4)

def _score_growth(revenue_growth: Optional[float]) -> float:
    """Score revenue YoY growth on a 0–1 scale.

    > 10%  → positive (0.75–1.0)
    0–10%  → neutral  (0.5–0.75)
    < 0%   → negative (0–0.5)
    None   → neutral  (0.5)
    """
    if revenue_growth is None:
        return 0.5

    g = revenue_growth   # percent, e.g. 15.0 = +15 %
    if g >= 20:
        return 1.0
    if g >= 10:
        return 0.75
    if g >= 0:
        return 0.5
    if g >= -10:
        return 0.25
    return 0.0


# ---------------------------------------------------------------------------
# Reason builder
# ---------------------------------------------------------------------------

def _build_reasons(
    eps_quarters:   list[float],
    eps_score:      float,
    pe_score:       float,
    growth_score:   float,
    current_pe:     Optional[float],
    avg_pe:         Optional[float],
    revenue_growth: Optional[float],
) -> list[str]:
    reasons: list[str] = []

    # EPS reason
    if not eps_quarters:
        reasons.append("EPS data unavailable")
    elif eps_score >= 0.7:
        reasons.append("EPS trend consistently improving (YoY)")
    elif eps_score >= 0.5:
        reasons.append("EPS trend mixed or flat")
    else:
        reasons.append("EPS trend declining")

    # PE reason
    if current_pe is not None and avg_pe is not None and avg_pe > 0:
        ratio = current_pe / avg_pe
        pct = (ratio - 1) * 100

        if ratio > 1.5:
            reasons.append(
                f"PE significantly above historical average: {current_pe:.1f}× vs {avg_pe:.1f}× (+{pct:.0f}%)"
            )
        elif ratio > 1.1:
            reasons.append(
                f"PE above historical average: {current_pe:.1f}× vs {avg_pe:.1f}× (+{pct:.0f}%)"
            )
        elif ratio < 0.9:
            reasons.append(
                f"PE below historical average: {current_pe:.1f}× vs {avg_pe:.1f}× ({pct:.0f}%)"
            )
        else:
            reasons.append(
                f"PE near historical average: {current_pe:.1f}× vs {avg_pe:.1f}×"
            )
    else:
        reasons.append("PE data unavailable")

    # Growth reason
    if revenue_growth is not None:
        if growth_score >= 0.75:
            reasons.append(f"Revenue YoY +{revenue_growth:.1f}% — strong growth")
        elif growth_score >= 0.5:
            reasons.append(f"Revenue YoY +{revenue_growth:.1f}% — moderate growth")
        else:
            reasons.append(f"Revenue YoY {revenue_growth:.1f}% — weak or negative growth")
    else:
        reasons.append("Revenue growth not provided — scored neutral")

    return reasons[:3]   # cap at 3


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_quarterly_eps(daily: pd.DataFrame, max_quarters: int) -> list[float]:
    """Extract distinct quarterly EPS values from a forward-filled daily column.

    Returns up to *max_quarters* values, oldest first.
    """
    if "eps" not in daily.columns or daily.empty:
        return []

    eps_series = daily["eps"].dropna()
    if eps_series.empty:
        return []

    # Detect quarter boundaries by change in forward-filled value
    changes = eps_series[eps_series.ne(eps_series.shift())]
    values  = changes.values.tolist()

    # Most recent N quarters
    return [float(v) for v in values[-max_quarters:]]


def _pe_stats(daily: pd.DataFrame) -> tuple[Optional[float], Optional[float]]:
    """Return (current_pe, historical_average_pe)."""
    if "pe" not in daily.columns or daily.empty:
        return None, None

    pe_series = daily["pe"].dropna()
    if pe_series.empty:
        return None, None

    current = round(float(pe_series.iloc[-1]), 2)
    avg     = round(float(pe_series.mean()), 2)
    return current, avg


def _classify(score: float) -> LongTermClass:
    if score >= _STRONG_LONG_THRESHOLD:
        return LongTermClass.STRONG_LONG
    if score >= _NEUTRAL_THRESHOLD:
        return LongTermClass.NEUTRAL
    return LongTermClass.WEAK
