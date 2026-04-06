"""Aggregate signals from multiple strategies into a single scored DataFrame.

Usage
-----
    from signals.aggregator import aggregate, AggregationWeights

    weights = AggregationWeights(price=0.4, margin=0.3, davis=0.3)
    result  = aggregate(
        price_signals=pv_signals,
        margin_signals=mt_signals,
        davis_signals=dd_signals,
        weights=weights,
    )
"""

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from signals.base import Signal

# Strategy name constants — must match Signal.signal_name values
_PRICE_VOLUME = "price_volume"
_MARGIN_TREND = "margin_trend"
_DAVIS_DOUBLE = "davis_double"


@dataclass
class AggregationWeights:
    """Weights applied to each strategy's score in the weighted sum.

    Weights are normalised internally so they do not need to sum to 1.0,
    but all must be non-negative.

    Attributes
    ----------
    price  : Weight for price_volume signals.
    margin : Weight for margin_trend signals.
    davis  : Weight for davis_double signals.
    """
    price:  float = 0.4
    margin: float = 0.2
    davis:  float = 0.4

    def __post_init__(self) -> None:
        for name, val in [("price", self.price), ("margin", self.margin), ("davis", self.davis)]:
            if val < 0:
                raise ValueError(f"Weight '{name}' must be non-negative, got {val}")
        if self.price + self.margin + self.davis == 0:
            raise ValueError("At least one weight must be non-zero")


def aggregate(
    price_signals:  list[Signal],
    margin_signals: list[Signal],
    davis_signals:  list[Signal],
    weights: Optional[AggregationWeights] = None,
) -> pd.DataFrame:
    """Combine signals from three strategies into a single scored DataFrame.

    Missing signals for a (stock_id, date) pair are treated as score=0.
    Scores from all three strategies are always included as columns so
    downstream consumers can inspect individual contributions.

    Parameters
    ----------
    price_signals  : Output of PriceVolumeStrategy.generate().
    margin_signals : Output of MarginTrendStrategy.generate().
    davis_signals  : Output of DavisDoubleStrategy.generate().
    weights        : AggregationWeights instance. Defaults to equal weights (1:1:1).

    Returns
    -------
    DataFrame with columns:
        stock_id, date,
        price_volume_score, margin_trend_score, davis_double_score,
        final_score
    Sorted by (date, stock_id). Empty signals produce an empty DataFrame.
    """
    if weights is None:
        weights = AggregationWeights()

    frames = [
        _to_frame(price_signals,  _PRICE_VOLUME),
        _to_frame(margin_signals, _MARGIN_TREND),
        _to_frame(davis_signals,  _DAVIS_DOUBLE),
    ]

    # Drop empty frames before merging
    non_empty = [f for f in frames if not f.empty]
    if not non_empty:
        return _empty_result()

    # Outer-join all frames on (stock_id, date); missing scores → 0
    result = non_empty[0]
    for frame in non_empty[1:]:
        result = result.merge(frame, on=["stock_id", "date"], how="outer")

    score_cols = [
        f"{_PRICE_VOLUME}_score",
        f"{_MARGIN_TREND}_score",
        f"{_DAVIS_DOUBLE}_score",
    ]
    for col in score_cols:
        if col not in result.columns:
            result[col] = 0.0
    result[score_cols] = result[score_cols].fillna(0.0)

    # Weighted sum, normalised by total weight
    total = weights.price + weights.margin + weights.davis
    result["final_score"] = (
        weights.price  * result[f"{_PRICE_VOLUME}_score"]
        + weights.margin * result[f"{_MARGIN_TREND}_score"]
        + weights.davis  * result[f"{_DAVIS_DOUBLE}_score"]
    ) / total

    result["final_score"] = result["final_score"].round(4)

    return (
        result[["stock_id", "date"] + score_cols + ["final_score"]]
        .sort_values(["date", "stock_id"])
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_frame(signals: list[Signal], strategy_name: str) -> pd.DataFrame:
    """Convert a list of Signals to a (stock_id, date, <name>_score) DataFrame.

    Duplicate (stock_id, date) pairs are resolved by keeping the highest score,
    which handles edge cases where a strategy emits more than one signal per day.
    """
    if not signals:
        return pd.DataFrame(columns=["stock_id", "date", f"{strategy_name}_score"])

    df = pd.DataFrame([
        {"stock_id": s.stock_id, "date": s.date, "score": s.score}
        for s in signals
    ])

    # Keep the highest score per (stock_id, date)
    df = (
        df.groupby(["stock_id", "date"], as_index=False)["score"]
        .max()
        .rename(columns={"score": f"{strategy_name}_score"})
    )
    return df


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "stock_id", "date",
        f"{_PRICE_VOLUME}_score",
        f"{_MARGIN_TREND}_score",
        f"{_DAVIS_DOUBLE}_score",
        "final_score",
    ])
