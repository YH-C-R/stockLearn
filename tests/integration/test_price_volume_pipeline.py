"""Integration test: fetch → price-volume strategy → signal validation."""

from datetime import date

import pytest

from data.fetchers.price import fetch_daily_price
from signals.base import Signal, SignalDirection
from strategies.price_volume import PriceVolumeStrategy

STOCK_ID   = "2330"
START_DATE = date(2024, 1, 1)
END_DATE   = date(2024, 12, 31)


@pytest.fixture(scope="module")
def signals():
    df = fetch_daily_price(STOCK_ID, start_date=START_DATE, end_date=END_DATE)
    strategy = PriceVolumeStrategy()
    return strategy.generate(df)


# ---------------------------------------------------------------------------
# Pipeline completes
# ---------------------------------------------------------------------------

def test_pipeline_returns_a_list(signals):
    assert isinstance(signals, list)


def test_pipeline_produces_signals(signals):
    assert len(signals) > 0, "Expected at least one signal for 2330 over a full year"


# ---------------------------------------------------------------------------
# Signal output format
# ---------------------------------------------------------------------------

def test_all_signals_are_signal_instances(signals):
    assert all(isinstance(s, Signal) for s in signals)


def test_signal_stock_id_is_correct(signals):
    assert all(s.stock_id == STOCK_ID for s in signals)


def test_signal_dates_within_range(signals):
    assert all(START_DATE <= s.date <= END_DATE for s in signals)


def test_signal_name_is_correct(signals):
    assert all(s.signal_name == "price_volume" for s in signals)


def test_signal_scores_are_valid(signals):
    valid_scores = {0.4, 0.8, 1.0}
    assert all(s.score in valid_scores for s in signals)


def test_all_signals_are_bullish(signals):
    assert all(s.direction == SignalDirection.BULLISH for s in signals)


def test_signal_value_is_positive(signals):
    assert all(s.signal_value > 0 for s in signals)


def test_signal_metadata_keys_present(signals):
    required_keys = {
        "rolling_high", "avg_volume", "volume_ratio",
        "confirmation", "price_window", "volume_window", "volume_surge_mult",
    }
    for s in signals:
        assert required_keys <= s.metadata.keys(), (
            f"Signal on {s.date} missing metadata keys: "
            f"{required_keys - s.metadata.keys()}"
        )
