"""Compute a combined score for a single stock from multi-strategy signals.

Delegates aggregation to ``signals.aggregator.aggregate()`` so scoring logic
stays in one place.  Adds a ``ScoreSnapshot`` — the most recent scored row —
for quick inspection without reading the full time-series.

Usage
-----
    from data.single_stock_loader import load_stock
    from analysis.single_stock_analysis import analyze_stock
    from analysis.single_stock_scoring import score_stock, ScoringConfig

    data     = load_stock("2330", start, end, token=TOKEN)
    analysis = analyze_stock(data)
    scored   = score_stock(analysis)

    print(scored.snapshot)    # latest ScoreSnapshot
    print(scored.history)     # full time-series DataFrame
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd

from analysis.single_stock_analysis import AnalysisResult
from signals.aggregator import AggregationWeights, aggregate


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ScoringConfig:
    """Weights and filters for combining strategy scores.

    Attributes
    ----------
    weights         : How each strategy contributes to final_score.
                      Defaults match the project-wide CombinedStrategyConfig
                      (price=0.4, margin=0.2, davis=0.4).
    min_final_score : Rows below this threshold are excluded from ``history``.
                      Set to 0.0 to keep all scored rows.
    """
    weights:         AggregationWeights = field(
        default_factory=lambda: AggregationWeights(price=0.4, margin=0.2, davis=0.4)
    )
    min_final_score: float = 0.0


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

@dataclass
class ScoreSnapshot:
    """The most recent scored row for a stock.

    Attributes
    ----------
    date            : Date of the most recent signal.
    pv_score        : price_volume score on that date (0.0 if no signal).
    mt_score        : margin_trend score on that date (0.0 if no signal).
    dd_score        : davis_double score on that date (0.0 if no signal).
    final_score     : Weighted combined score.
    """
    date:        date
    pv_score:    float
    mt_score:    float
    dd_score:    float
    final_score: float

    def as_dict(self) -> dict:
        return {
            "date":        self.date,
            "pv_score":    self.pv_score,
            "mt_score":    self.mt_score,
            "dd_score":    self.dd_score,
            "final_score": self.final_score,
        }


@dataclass
class StockScoreResult:
    """Output of score_stock().

    Attributes
    ----------
    stock_id  : Stock ticker.
    snapshot  : Latest scored row, or None if no signals exist.
    history   : Full time-series DataFrame with columns:
                date, price_volume_score, margin_trend_score,
                davis_double_score, final_score.
                Filtered by ScoringConfig.min_final_score.
    """
    stock_id: str
    snapshot: Optional[ScoreSnapshot]
    history:  pd.DataFrame

    def summary(self) -> dict:
        """Quick overview for printing."""
        if self.snapshot is None:
            return {"stock_id": self.stock_id, "scored_dates": 0, "snapshot": None}
        return {
            "stock_id":     self.stock_id,
            "scored_dates": len(self.history),
            "snapshot":     self.snapshot.as_dict(),
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_stock(
    analysis: AnalysisResult,
    config:   Optional[ScoringConfig] = None,
) -> StockScoreResult:
    """Combine signals from all strategies into a scored time-series.

    Parameters
    ----------
    analysis : Output of ``analyze_stock()``.
    config   : ScoringConfig.  Defaults to ScoringConfig().

    Returns
    -------
    StockScoreResult with a full ``history`` DataFrame and a ``snapshot``
    of the latest scored row.  Both are empty/None when no signals exist.
    """
    if config is None:
        config = ScoringConfig()

    scored = aggregate(
        price_signals  = analysis.pv_signals,
        margin_signals = analysis.mt_signals,
        davis_signals  = analysis.dd_signals,
        weights        = config.weights,
    )

    if scored.empty:
        return StockScoreResult(
            stock_id = analysis.stock_id,
            snapshot = None,
            history  = _empty_history(),
        )

    # Drop the stock_id column — redundant for single-stock context
    history = scored.drop(columns=["stock_id"], errors="ignore").copy()

    # Rename for readability in single-stock context
    history = history.rename(columns={
        "price_volume_score": "pv_score",
        "margin_trend_score": "mt_score",
        "davis_double_score": "dd_score",
    })

    # Apply score filter
    if config.min_final_score > 0.0:
        history = history[history["final_score"] >= config.min_final_score]

    history = history.reset_index(drop=True)

    snapshot = _make_snapshot(history) if not history.empty else None

    return StockScoreResult(
        stock_id = analysis.stock_id,
        snapshot = snapshot,
        history  = history,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_snapshot(history: pd.DataFrame) -> ScoreSnapshot:
    """Build a ScoreSnapshot from the last row of the history DataFrame."""
    row = history.iloc[-1]
    return ScoreSnapshot(
        date        = row["date"],
        pv_score    = float(row["pv_score"]),
        mt_score    = float(row["mt_score"]),
        dd_score    = float(row["dd_score"]),
        final_score = float(row["final_score"]),
    )


def _empty_history() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "date", "pv_score", "mt_score", "dd_score", "final_score"
    ])
