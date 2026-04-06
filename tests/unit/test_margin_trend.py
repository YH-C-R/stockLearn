"""Unit tests for strategies/margin_trend.py."""

from datetime import date

import pandas as pd
import pytest

from signals.base import SignalDirection
from strategies.margin_trend import MarginTrendStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_df(closes, margins, stock_id="2330", include_short=False):
    """Build merged-style price + margin DataFrames with 5-day window."""
    n = len(closes)
    dates = [date(2024, 1, i + 1) for i in range(n)]
    price_df = pd.DataFrame({
        "stock_id": stock_id,
        "date":     dates,
        "close":    closes,
    })
    margin_data = {
        "stock_id":                 stock_id,
        "date":                     dates,
        "margin_purchase_balance":  margins,
    }
    if include_short:
        margin_data["short_sale_balance"] = [1_000_000] * n
    margin_df = pd.DataFrame(margin_data)
    return price_df, margin_df


@pytest.fixture()
def strategy():
    return MarginTrendStrategy(
        window=3,
        surge_threshold=0.05,
        unwind_threshold=0.03,
        min_abs_score=0.5,
    )


# ---------------------------------------------------------------------------
# Column requirements
# ---------------------------------------------------------------------------

def test_missing_margin_balance_raises(strategy):
    price_df, margin_df = make_df([100]*6, [1_000_000]*6)
    margin_df = margin_df.drop(columns=["margin_purchase_balance"])
    with pytest.raises(ValueError, match="missing columns"):
        strategy.generate(price_df, margin_df=margin_df)


def test_short_sale_balance_optional(strategy):
    """Strategy should work with or without short_sale_balance column."""
    price_df, margin_df = make_df(
        [100, 100, 100, 105, 110, 115],
        [1_000_000] * 3 + [900_000] * 3,
    )
    # Should not raise even without short_sale_balance
    signals = strategy.generate(price_df, margin_df=margin_df)
    assert isinstance(signals, list)


def test_short_sale_balance_included_in_metadata_when_present(strategy):
    price_df, margin_df = make_df(
        [100, 100, 100, 105, 110, 115],
        [1_000_000] * 3 + [900_000] * 3,
        include_short=True,
    )
    signals = strategy.generate(price_df, margin_df=margin_df)
    for s in signals:
        assert "short_sale_balance" in (s.metadata or {})


# ---------------------------------------------------------------------------
# Signal conditions
# ---------------------------------------------------------------------------

def test_bullish_signal_price_up_margin_down(strategy):
    # price rises, margin falls → healthy rally → bullish
    price_df, margin_df = make_df(
        closes  = [100, 100, 100, 110, 115, 120],
        margins = [1_000_000, 1_000_000, 1_000_000, 900_000, 880_000, 860_000],
    )
    signals = strategy.generate(price_df, margin_df=margin_df)
    bullish = [s for s in signals if s.direction == SignalDirection.BULLISH]
    assert len(bullish) > 0


def test_bearish_signal_price_down_margin_up(strategy):
    # price falls, margin surges → dangerous → bearish
    price_df, margin_df = make_df(
        closes  = [110, 110, 110, 100, 95, 90],
        margins = [1_000_000, 1_000_000, 1_000_000, 1_100_000, 1_150_000, 1_200_000],
    )
    signals = strategy.generate(price_df, margin_df=margin_df)
    bearish = [s for s in signals if s.direction == SignalDirection.BEARISH]
    assert len(bearish) > 0


def test_no_signal_when_both_flat(strategy):
    price_df, margin_df = make_df(
        closes  = [100] * 6,
        margins = [1_000_000] * 6,
    )
    signals = strategy.generate(price_df, margin_df=margin_df)
    assert signals == []


def test_min_abs_score_filters_weak_signals():
    """Raising min_abs_score should reduce or eliminate signals."""
    price_df, margin_df = make_df(
        closes  = [100, 100, 100, 105, 108, 110],
        margins = [1_000_000, 1_000_000, 1_000_000, 980_000, 970_000, 960_000],
    )
    low_bar  = MarginTrendStrategy(window=3, min_abs_score=0.1)
    high_bar = MarginTrendStrategy(window=3, min_abs_score=0.9)
    assert len(low_bar.generate(price_df, margin_df=margin_df)) >= \
           len(high_bar.generate(price_df, margin_df=margin_df))


# ---------------------------------------------------------------------------
# Configurable weights
# ---------------------------------------------------------------------------

def test_custom_weights_change_score(strategy):
    """Equal vs unequal weights should produce different scores."""
    price_df, margin_df = make_df(
        closes  = [110, 110, 110, 100, 95, 90],
        margins = [1_000_000, 1_000_000, 1_000_000, 1_100_000, 1_150_000, 1_200_000],
    )
    equal   = MarginTrendStrategy(window=3, margin_weight=0.5, divergence_weight=0.5,
                                  min_abs_score=0.1)
    skewed  = MarginTrendStrategy(window=3, margin_weight=0.9, divergence_weight=0.1,
                                  min_abs_score=0.1)
    s_equal  = equal.generate(price_df, margin_df=margin_df)
    s_skewed = skewed.generate(price_df, margin_df=margin_df)

    if s_equal and s_skewed:
        # Scores should differ when weights differ
        scores_equal  = {s.date: s.score for s in s_equal}
        scores_skewed = {s.date: s.score for s in s_skewed}
        shared_dates  = set(scores_equal) & set(scores_skewed)
        if shared_dates:
            d = next(iter(shared_dates))
            assert scores_equal[d] != scores_skewed[d]


def test_zero_weight_sum_raises():
    with pytest.raises(ValueError, match="must not sum to zero"):
        MarginTrendStrategy(margin_weight=0.5, divergence_weight=-0.5)


def test_weights_in_metadata(strategy):
    price_df, margin_df = make_df(
        closes  = [100, 100, 100, 110, 115, 120],
        margins = [1_000_000, 1_000_000, 1_000_000, 900_000, 880_000, 860_000],
    )
    signals = strategy.generate(price_df, margin_df=margin_df)
    for s in signals:
        meta = s.metadata or {}
        assert "margin_weight"    in meta
        assert "divergence_weight" in meta


# ---------------------------------------------------------------------------
# Score bounds
# ---------------------------------------------------------------------------

def test_all_scores_within_bounds(strategy):
    price_df, margin_df = make_df(
        closes  = [100, 100, 100, 110, 90, 120],
        margins = [1_000_000, 1_000_000, 1_000_000, 1_200_000, 800_000, 900_000],
    )
    signals = strategy.generate(price_df, margin_df=margin_df)
    for s in signals:
        assert -1.0 <= s.score <= 1.0


# ---------------------------------------------------------------------------
# Insufficient history
# ---------------------------------------------------------------------------

def test_insufficient_history_produces_no_signal(strategy):
    price_df, margin_df = make_df(
        closes  = [100, 110],
        margins = [1_000_000, 900_000],
    )
    assert strategy.generate(price_df, margin_df=margin_df) == []
