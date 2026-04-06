from datetime import date

import pandas as pd
import pytest

from signals.base import SignalDirection
from strategies.price_volume import PriceVolumeStrategy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Use small windows so a handful of rows is enough to produce signals.
@pytest.fixture()
def strategy():
    return PriceVolumeStrategy(
        price_window=3,
        volume_window=3,
        volume_surge_mult=2.0,
        min_close=1.0,
    )


def make_df(closes, highs, volumes, stock_id="2330"):
    """Build a minimal price DataFrame with sequential dates."""
    n = len(closes)
    return pd.DataFrame({
        "stock_id": stock_id,
        "date":     [date(2024, 1, i + 1) for i in range(n)],
        "open":     closes,   # not used by strategy; set equal to close
        "high":     highs,
        "low":      closes,   # not used by strategy; set equal to close
        "close":    closes,
        "volume":   volumes,
    })


# ---------------------------------------------------------------------------
# Core signal conditions
# ---------------------------------------------------------------------------

def test_breakout_with_volume_surge_generates_signal(strategy):
    # Days 1-3: baseline prices (high=100) and normal volume (1000)
    # Day 4: close=110 breaks above rolling high=100, volume=3000 = 3× avg → surge
    df = make_df(
        closes  = [100, 100, 100, 110],
        highs   = [100, 100, 100, 110],
        volumes = [1000, 1000, 1000, 3000],
    )
    signals = strategy.generate(df)
    assert len(signals) == 1
    assert signals[0].score == 0.8   # volume_ratio=3.0 ≥ 2.0× but < 4.0×


def test_breakout_with_strong_surge_scores_1(strategy):
    # volume=5000 = 5× avg (≥ 2× surge_mult=2.0 → double_surge=4.0) → score 1.0
    df = make_df(
        closes  = [100, 100, 100, 110],
        highs   = [100, 100, 100, 110],
        volumes = [1000, 1000, 1000, 5000],
    )
    signals = strategy.generate(df)
    assert len(signals) == 1
    assert signals[0].score == 1.0


def test_breakout_without_volume_scores_0_4(strategy):
    # volume=1000 same as avg → volume_ratio=1.0 < surge_mult=2.0 → unconfirmed
    df = make_df(
        closes  = [100, 100, 100, 110],
        highs   = [100, 100, 100, 110],
        volumes = [1000, 1000, 1000, 1000],
    )
    signals = strategy.generate(df)
    assert len(signals) == 1
    assert signals[0].score == 0.4


def test_no_breakout_produces_no_signal(strategy):
    # Close stays flat at 100 — never exceeds rolling high of 100
    df = make_df(
        closes  = [100, 100, 100, 100],
        highs   = [100, 100, 100, 100],
        volumes = [1000, 1000, 1000, 5000],
    )
    signals = strategy.generate(df)
    assert signals == []


def test_close_below_rolling_high_produces_no_signal(strategy):
    # Day 4 close=90, rolling high=100 → no breakout
    df = make_df(
        closes  = [100, 100, 100, 90],
        highs   = [100, 100, 100, 100],
        volumes = [1000, 1000, 1000, 5000],
    )
    signals = strategy.generate(df)
    assert signals == []


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------

def test_signal_has_expected_fields(strategy):
    df = make_df(
        closes  = [100, 100, 100, 110],
        highs   = [100, 100, 100, 110],
        volumes = [1000, 1000, 1000, 3000],
    )
    sig = strategy.generate(df)[0]

    assert sig.stock_id    == "2330"
    assert sig.signal_name == "price_volume"
    assert sig.date        == date(2024, 1, 4)
    assert sig.signal_value == 110.0
    assert -1.0 <= sig.score <= 1.0
    assert sig.direction   == SignalDirection.BULLISH


def test_signal_metadata_contains_expected_keys(strategy):
    df = make_df(
        closes  = [100, 100, 100, 110],
        highs   = [100, 100, 100, 110],
        volumes = [1000, 1000, 1000, 3000],
    )
    meta = strategy.generate(df)[0].metadata

    for key in ("rolling_high", "avg_volume", "volume_ratio", "confirmation",
                "price_window", "volume_window", "volume_surge_mult"):
        assert key in meta, f"metadata missing key: {key}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_insufficient_history_produces_no_signal(strategy):
    # Only 2 rows — not enough to fill price_window=3
    df = make_df(
        closes  = [100, 110],
        highs   = [100, 110],
        volumes = [1000, 5000],
    )
    signals = strategy.generate(df)
    assert signals == []


def test_min_close_filter_skips_cheap_stocks():
    strategy = PriceVolumeStrategy(price_window=3, volume_window=3,
                                   volume_surge_mult=2.0, min_close=50.0)
    df = make_df(
        closes  = [10, 10, 10, 12],   # all below min_close=50
        highs   = [10, 10, 10, 12],
        volumes = [1000, 1000, 1000, 5000],
    )
    assert strategy.generate(df) == []


def test_missing_required_column_raises(strategy):
    df = make_df(
        closes  = [100, 100, 100, 110],
        highs   = [100, 100, 100, 110],
        volumes = [1000, 1000, 1000, 3000],
    ).drop(columns=["volume"])

    with pytest.raises(ValueError, match="missing columns"):
        strategy.generate(df)


def test_multi_stock_signals_are_attributed_correctly(strategy):
    df_a = make_df([100, 100, 100, 110], [100, 100, 100, 110],
                   [1000, 1000, 1000, 3000], stock_id="2330")
    df_b = make_df([200, 200, 200, 200], [200, 200, 200, 200],
                   [1000, 1000, 1000, 5000], stock_id="2317")

    signals = strategy.generate(pd.concat([df_a, df_b], ignore_index=True))

    # Only 2330 breaks out; 2317 stays flat
    assert len(signals) == 1
    assert signals[0].stock_id == "2330"
