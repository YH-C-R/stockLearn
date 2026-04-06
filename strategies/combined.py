"""Combined strategy: runs all three strategies and aggregates their signals."""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd

from signals.aggregator import AggregationWeights, aggregate
from signals.base import Signal, make_signal
from strategies.davis_double import DavisDoubleStrategy
from strategies.margin_trend import MarginTrendStrategy
from strategies.price_volume import PriceVolumeStrategy


@dataclass
class CombinedStrategyConfig:
    """Configuration for all sub-strategies and aggregation weights.

    Sub-strategy configs
    --------------------
    pv_*     : PriceVolumeStrategy parameters.
    mt_*     : MarginTrendStrategy parameters.
    dd_*     : DavisDoubleStrategy parameters.

    Aggregation weights
    -------------------
    weights  : AggregationWeights controlling how scores are combined.
               Defaults to price=0.4, margin=0.2, davis=0.4.
               margin_trend fires frequently (state-based), so its weight
               is intentionally lower.  davis_double is rare but high-conviction
               (event-based), so it shares equal weight with price_volume.

    Margin cooldown
    ---------------
    mt_cooldown_days : After a margin_trend signal fires for a stock, suppress
                       further margin signals for that stock for this many
                       trading days.  Prevents a continuous margin state from
                       contributing every single day.
                       Set to 0 to disable (original behaviour).

    Davis persistence
    -----------------
    dd_persistence_days : When > 0, each davis_double signal is replicated
                          forward for this many additional trading days.
                          This prevents a quarterly event signal from
                          contributing to the final score on only one day.
                          Set to 0 to disable (original behaviour).

    Output filter
    -------------
    min_final_score : Only rows with final_score >= this are returned.
                      Rows below this threshold are dropped before ranking.
    """
    # PriceVolumeStrategy
    pv_price_window: int        = 20
    pv_volume_window: int       = 20
    pv_volume_surge_mult: float = 2.0
    pv_min_close: float         = 5.0
    pv_max_breakout_pct: float  = 0.08
    pv_emit_weak_signals: bool  = True

    # MarginTrendStrategy
    mt_window: int              = 5
    mt_surge_threshold: float   = 0.05
    mt_unwind_threshold: float  = 0.03
    mt_min_abs_score: float     = 0.5
    mt_margin_weight: float     = 0.5
    mt_divergence_weight: float = 0.5
    mt_cooldown_days: int       = 10   # suppress repeated margin signals per stock

    # DavisDoubleStrategy
    dd_ma_window: int           = 60
    dd_yoy_threshold: float     = 0.30
    dd_max_ma_distance: float   = 0.15
    dd_persistence_days: int    = 5    # keep davis signal active for N extra trading days

    # Aggregation — margin is down-weighted vs price/davis (fires much more often)
    weights: AggregationWeights = field(
        default_factory=lambda: AggregationWeights(price=0.4, margin=0.2, davis=0.4)
    )

    # Output — drop weak combined scores before ranking
    min_final_score: float      = 0.3


class CombinedStrategy:
    """Run price_volume, margin_trend, and davis_double; aggregate into one DataFrame.

    This class is intentionally not a subclass of BaseStrategy because its
    output is a DataFrame (not a list[Signal]) — the aggregator merges signals
    across strategies and dates into a tabular format.

    Parameters
    ----------
    config : CombinedStrategyConfig. Defaults to all strategy defaults.
    """

    def __init__(self, config: Optional[CombinedStrategyConfig] = None) -> None:
        self.config = config or CombinedStrategyConfig()
        cfg = self.config

        self._pv = PriceVolumeStrategy(
            price_window=cfg.pv_price_window,
            volume_window=cfg.pv_volume_window,
            volume_surge_mult=cfg.pv_volume_surge_mult,
            min_close=cfg.pv_min_close,
            max_breakout_pct=cfg.pv_max_breakout_pct,
            emit_weak_signals=cfg.pv_emit_weak_signals,
        )
        self._mt = MarginTrendStrategy(
            window=cfg.mt_window,
            surge_threshold=cfg.mt_surge_threshold,
            unwind_threshold=cfg.mt_unwind_threshold,
            min_abs_score=cfg.mt_min_abs_score,
            margin_weight=cfg.mt_margin_weight,
            divergence_weight=cfg.mt_divergence_weight,
        )
        self._dd = DavisDoubleStrategy(
            ma_window=cfg.dd_ma_window,
            yoy_threshold=cfg.dd_yoy_threshold,
            max_ma_distance=cfg.dd_max_ma_distance,
        )

    def generate(
        self,
        price_df: pd.DataFrame,
        margin_df: Optional[pd.DataFrame] = None,
        fundamentals_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """Run all strategies and return an aggregated signal DataFrame.

        Parameters
        ----------
        price_df        : Daily OHLCV DataFrame. Required.
        margin_df       : Daily margin DataFrame. If None, margin_trend is skipped.
        fundamentals_df : Quarterly EPS DataFrame. If None, davis_double is skipped.

        Returns
        -------
        DataFrame with columns:
            stock_id, date,
            price_volume_score, margin_trend_score, davis_double_score,
            final_score
        Filtered to rows where final_score >= config.min_final_score.
        Sorted by (date, stock_id).
        """
        pv_signals: list[Signal] = self._pv.generate(price_df)

        mt_signals: list[Signal] = []
        if margin_df is not None:
            mt_signals = self._mt.generate(price_df, margin_df=margin_df)
            if self.config.mt_cooldown_days > 0:
                mt_signals = _apply_cooldown(mt_signals, self.config.mt_cooldown_days)

        dd_signals: list[Signal] = []
        if fundamentals_df is not None:
            dd_signals = self._dd.generate(price_df, fundamentals_df=fundamentals_df)
            if self.config.dd_persistence_days > 0:
                dd_signals = _persist_signals(dd_signals, price_df, self.config.dd_persistence_days)

        result = aggregate(
            price_signals=pv_signals,
            margin_signals=mt_signals,
            davis_signals=dd_signals,
            weights=self.config.weights,
        )

        if self.config.min_final_score > 0.0 and not result.empty:
            result = result[result["final_score"] >= self.config.min_final_score]

        return result.reset_index(drop=True)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def rank(self, result: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
        """Rank stocks by final_score within each date and return the top N.

        Parameters
        ----------
        result : Output of generate().
        top_n  : Maximum number of stocks to select per date.

        Returns
        -------
        DataFrame with columns: stock_id, date, final_score, rank.
        One row per selected stock per date, sorted by (date, rank).
        """
        return rank_signals(result, top_n=top_n)

    def summary(self, result: pd.DataFrame) -> dict:
        """Return a quick summary dict for a result DataFrame.

        Parameters
        ----------
        result : Output of generate().

        Returns
        -------
        dict with total_signals, date_range, score_mean, score_max.
        """
        if result.empty:
            return {"total_signals": 0, "date_range": None,
                    "score_mean": None, "score_max": None}
        return {
            "total_signals": len(result),
            "date_range":    (result["date"].min(), result["date"].max()),
            "score_mean":    round(result["final_score"].mean(), 4),
            "score_max":     round(result["final_score"].max(), 4),
        }


# ---------------------------------------------------------------------------
# Margin cooldown helper
# ---------------------------------------------------------------------------

def _apply_cooldown(signals: list[Signal], cooldown_days: int) -> list[Signal]:
    """Suppress repeated signals for the same stock within a cooldown window.

    For each stock, only the first signal in any cooldown_days-wide window is
    kept.  Subsequent signals that fall inside the window are dropped.  Once
    the window expires a new signal can fire.

    This converts margin_trend's continuous state-based output into a more
    event-like stream, preventing it from contributing every single trading day.

    Parameters
    ----------
    signals      : Raw list of Signal objects (any strategy).
    cooldown_days: Calendar days to suppress after each kept signal.
                   Uses calendar days (not trading days) for simplicity.
    """
    if not signals or cooldown_days <= 0:
        return signals

    from datetime import timedelta

    # Process per stock in chronological order
    last_kept: dict[str, date] = {}
    kept: list[Signal] = []

    for sig in sorted(signals, key=lambda s: (s.stock_id, s.date)):
        sig_date: date = (
            sig.date if isinstance(sig.date, date)
            else pd.Timestamp(sig.date).date()
        )
        prev = last_kept.get(sig.stock_id)
        if prev is None or (sig_date - prev).days > cooldown_days:
            kept.append(sig)
            last_kept[sig.stock_id] = sig_date

    return kept


# ---------------------------------------------------------------------------
# Davis persistence helper
# ---------------------------------------------------------------------------

def _persist_signals(
    signals: list[Signal],
    price_df: pd.DataFrame,
    persistence_days: int,
) -> list[Signal]:
    """Extend each signal forward by persistence_days additional trading days.

    The original signal date is kept.  For each subsequent trading day up to
    persistence_days, a copy of the signal is appended with a ``persisted=True``
    marker in its metadata.

    The aggregator's dedup logic (keep max score per (stock_id, date)) ensures
    that a persisted copy never overwrites a genuine signal on the same date.
    """
    if not signals or persistence_days <= 0:
        return signals

    # Build a sorted list of all trading dates from price_df
    trading_dates: list[date] = sorted(
        pd.to_datetime(price_df["date"]).dt.date.unique()
    )
    date_index: dict[date, int] = {d: i for i, d in enumerate(trading_dates)}

    expanded = list(signals)
    for sig in signals:
        sig_date: date = (
            sig.date if isinstance(sig.date, date)
            else pd.Timestamp(sig.date).date()
        )
        base_idx = date_index.get(sig_date)
        if base_idx is None:
            continue

        for offset in range(1, persistence_days + 1):
            next_idx = base_idx + offset
            if next_idx >= len(trading_dates):
                break
            expanded.append(make_signal(
                stock_id=sig.stock_id,
                date=trading_dates[next_idx],
                signal_name=sig.signal_name,
                signal_value=sig.signal_value,
                score=sig.score,
                metadata={
                    **(sig.metadata or {}),
                    "persisted": True,
                    "origin_date": str(sig_date),
                },
            ))

    return expanded


# ---------------------------------------------------------------------------
# Standalone ranking helper (usable without CombinedStrategy)
# ---------------------------------------------------------------------------

def rank_signals(result: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """Rank stocks by final_score within each date and return the top N.

    Ties are broken by stock_id alphabetically so the output is deterministic.

    Parameters
    ----------
    result : DataFrame produced by aggregate() or CombinedStrategy.generate().
             Must contain columns: stock_id, date, final_score.
    top_n  : Maximum number of stocks to select per date. If fewer stocks
             have signals on a given date, all of them are returned.

    Returns
    -------
    DataFrame with columns: date, stock_id, final_score, rank.
    Sorted by (date, rank). Empty input returns an empty DataFrame.

    Example
    -------
        selected = rank_signals(result, top_n=5)
        # date        stock_id  final_score  rank
        # 2024-05-15  2330      0.82         1
        # 2024-05-15  2454      0.71         2
        # 2024-05-15  2317      0.65         3
    """
    if result.empty:
        return pd.DataFrame(columns=["date", "stock_id", "final_score", "rank"])

    required = {"stock_id", "date", "final_score"}
    missing  = required - set(result.columns)
    if missing:
        raise ValueError(f"rank_signals: result DataFrame missing columns: {missing}")

    ranked = (
        result[["stock_id", "date", "final_score"]]
        .sort_values(["date", "final_score", "stock_id"],
                     ascending=[True, False, True])   # score desc, ticker asc for ties
        .copy()
    )

    ranked["rank"] = (
        ranked.groupby("date")["final_score"]
        .rank(method="first", ascending=False)
        .astype(int)
    )

    top = ranked[ranked["rank"] <= top_n].reset_index(drop=True)
    return top[["date", "stock_id", "final_score", "rank"]]
