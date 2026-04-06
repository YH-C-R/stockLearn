from datetime import date

import pandas as pd
import pytest

from signals.base import SignalDirection
from strategies.price_volume import PriceVolumeStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def strategy():
    return PriceVolumeStrategy(
        price_window=3,
        volume_window=3,
        volume_surge_mult=2.0,
        min_close=1.0,
        max_breakout_pct=0.08,
        emit_weak_signals=True,
    )


def make_df(closes, highs, volumes, stock_id="2330"):
    n = len(closes)
    return pd.DataFrame({
        "stock_id": stock_id,
        "date":     [date(2024, 1, i + 1) for i in range(n)],
        "open":     closes,
        "high":     highs,
        "low":      closes,
        "close":    closes,
        "volume":   volumes,
    })


# ---------------------------------------------------------------------------
# Core signal conditions
# ---------------------------------------------------------------------------

def test_breakout_with_volume_surge_generates_signal(strategy):
    df = make_df(
        closes  = [100, 100, 100, 110],
        highs   = [100, 100, 100, 110],
        volumes = [1000, 1000, 1000, 3000],
    )
    signals = strategy.generate(df)
    assert len(signals) == 1
    assert signals[0].score == 0.8


def test_breakout_with_strong_surge_scores_1(strategy):
    df = make_df(
        closes  = [100, 100, 100, 110],
        highs   = [100, 100, 100, 110],
        volumes = [1000, 1000, 1000, 5000],
    )
    signals = strategy.generate(df)
    assert len(signals) == 1
    assert signals[0].score == 1.0


def test_breakout_without_volume_scores_0_4(strategy):
    df = make_df(
        closes  = [100, 100, 100, 110],
        highs   = [100, 100, 100, 110],
        volumes = [1000, 1000, 1000, 1000],
    )
    signals = strategy.generate(df)
    assert len(signals) == 1
    assert signals[0].score == 0.4


def test_no_breakout_produces_no_signal(strategy):
    df = make_df(
        closes  = [100, 100, 100, 100],
        highs   = [100, 100, 100, 100],
        volumes = [1000, 1000, 1000, 5000],
    )
    assert strategy.generate(df) == []


def test_close_below_rolling_high_produces_no_signal(strategy):
    df = make_df(
        closes  = [100, 100, 100, 90],
        highs   = [100, 100, 100, 100],
        volumes = [1000, 1000, 1000, 5000],
    )
    assert strategy.generate(df) == []


# ---------------------------------------------------------------------------
# First-breakout-only (dedup)
# ---------------------------------------------------------------------------

def test_only_first_breakout_day_emits_signal(strategy):
    # Days 1-3: baseline. Days 4-6: price stays above rolling high.
    # Only day 4 (first breakout) should emit a signal.
    df = make_df(
        closes  = [100, 100, 100, 110, 112, 115],
        highs   = [100, 100, 100, 110, 112, 115],
        volumes = [1000, 1000, 1000, 3000, 3000, 3000],
    )
    signals = strategy.generate(df)
    assert len(signals) == 1
    assert signals[0].date == date(2024, 1, 4)


def test_new_breakout_fires_after_pullback(strategy):
    # Days 1-3 baseline; day 4 breakout; days 5-6 pull back below rolling high;
    # day 7 breaks out again → should emit a second signal.
    df = make_df(
        closes  = [100, 100, 100, 110,  95,  95, 115],
        highs   = [100, 100, 100, 110, 110, 110, 115],
        volumes = [1000, 1000, 1000, 3000, 1000, 1000, 3000],
    )
    signals = strategy.generate(df)
    assert len(signals) == 2
    assert signals[0].date == date(2024, 1, 4)
    assert signals[1].date == date(2024, 1, 7)


def test_continuous_breakout_emits_only_one_signal(strategy):
    # Price rises every day after breakout — stays in breakout for 4 days.
    df = make_df(
        closes  = [100, 100, 100, 105, 107, 109, 111],
        highs   = [100, 100, 100, 105, 107, 109, 111],
        volumes = [1000, 1000, 1000, 3000, 3000, 3000, 3000],
    )
    signals = strategy.generate(df)
    assert len(signals) == 1


# ---------------------------------------------------------------------------
# Overextended filter
# ---------------------------------------------------------------------------

def test_overextended_breakout_skipped():
    # breakout_pct = (116 / 100) - 1 = 0.16 > max_breakout_pct=0.08 → skipped
    strategy = PriceVolumeStrategy(price_window=3, volume_window=3,
                                   volume_surge_mult=2.0, max_breakout_pct=0.08)
    df = make_df(
        closes  = [100, 100, 100, 116],
        highs   = [100, 100, 100, 116],
        volumes = [1000, 1000, 1000, 5000],
    )
    assert strategy.generate(df) == []


def test_breakout_within_max_distance_passes():
    # breakout_pct = (107 / 100) - 1 = 0.07 < max_breakout_pct=0.08 → passes
    strategy = PriceVolumeStrategy(price_window=3, volume_window=3,
                                   volume_surge_mult=2.0, max_breakout_pct=0.08)
    df = make_df(
        closes  = [100, 100, 100, 107],
        highs   = [100, 100, 100, 107],
        volumes = [1000, 1000, 1000, 3000],
    )
    assert len(strategy.generate(df)) == 1


# ---------------------------------------------------------------------------
# emit_weak_signals flag
# ---------------------------------------------------------------------------

def test_weak_signal_suppressed_when_flag_false():
    strategy = PriceVolumeStrategy(price_window=3, volume_window=3,
                                   volume_surge_mult=2.0, emit_weak_signals=False)
    df = make_df(
        closes  = [100, 100, 100, 110],
        highs   = [100, 100, 100, 110],
        volumes = [1000, 1000, 1000, 1000],   # volume_ratio=1.0 < surge_mult
    )
    assert strategy.generate(df) == []


def test_strong_signal_emitted_regardless_of_flag():
    strategy = PriceVolumeStrategy(price_window=3, volume_window=3,
                                   volume_surge_mult=2.0, emit_weak_signals=False)
    df = make_df(
        closes  = [100, 100, 100, 110],
        highs   = [100, 100, 100, 110],
        volumes = [1000, 1000, 1000, 5000],
    )
    assert len(strategy.generate(df)) == 1


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_signal_has_expected_fields(strategy):
    df = make_df([100, 100, 100, 110], [100, 100, 100, 110], [1000, 1000, 1000, 3000])
    sig = strategy.generate(df)[0]
    assert sig.stock_id    == "2330"
    assert sig.signal_name == "price_volume"
    assert sig.date        == date(2024, 1, 4)
    assert sig.signal_value == 110.0
    assert -1.0 <= sig.score <= 1.0
    assert sig.direction   == SignalDirection.BULLISH


def test_signal_metadata_contains_expected_keys(strategy):
    df = make_df([100, 100, 100, 110], [100, 100, 100, 110], [1000, 1000, 1000, 3000])
    meta = strategy.generate(df)[0].metadata
    for key in ("rolling_high", "avg_volume", "volume_ratio", "volume_excess_pct",
                "breakout_pct", "confirmation", "price_window",
                "volume_window", "volume_surge_mult"):
        assert key in meta, f"metadata missing key: {key}"


def test_breakout_pct_in_metadata(strategy):
    df = make_df([100, 100, 100, 110], [100, 100, 100, 110], [1000, 1000, 1000, 3000])
    meta = strategy.generate(df)[0].metadata
    # breakout_pct = (110/100 - 1) * 100 = 10.0
    assert abs(meta["breakout_pct"] - 10.0) < 0.01


def test_volume_excess_pct_in_metadata(strategy):
    df = make_df([100, 100, 100, 110], [100, 100, 100, 110], [1000, 1000, 1000, 3000])
    meta = strategy.generate(df)[0].metadata
    # volume_ratio = 3.0 → excess = (3.0 - 1) * 100 = 200%
    assert abs(meta["volume_excess_pct"] - 200.0) < 0.01


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_insufficient_history_produces_no_signal(strategy):
    df = make_df([100, 110], [100, 110], [1000, 5000])
    assert strategy.generate(df) == []


def test_min_close_filter_skips_cheap_stocks():
    s = PriceVolumeStrategy(price_window=3, volume_window=3,
                            volume_surge_mult=2.0, min_close=50.0)
    df = make_df([10, 10, 10, 12], [10, 10, 10, 12], [1000, 1000, 1000, 5000])
    assert s.generate(df) == []


def test_missing_required_column_raises(strategy):
    df = make_df([100, 100, 100, 110], [100, 100, 100, 110],
                 [1000, 1000, 1000, 3000]).drop(columns=["volume"])
    with pytest.raises(ValueError, match="missing columns"):
        strategy.generate(df)


def test_multi_stock_signals_attributed_correctly(strategy):
    df_a = make_df([100, 100, 100, 110], [100, 100, 100, 110],
                   [1000, 1000, 1000, 3000], stock_id="2330")
    df_b = make_df([200, 200, 200, 200], [200, 200, 200, 200],
                   [1000, 1000, 1000, 5000], stock_id="2317")
    signals = strategy.generate(pd.concat([df_a, df_b], ignore_index=True))
    assert len(signals) == 1
    assert signals[0].stock_id == "2330"
