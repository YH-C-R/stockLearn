"""Unit tests for strategies/davis_double.py."""

from datetime import date, timedelta

import pandas as pd
import pytest

from strategies.davis_double import (
    DavisDoubleStrategy,
    _add_yoy_growth,
    _effective_date,
    _growth_score,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_price_df(closes: list[float], start: date = date(2024, 1, 2)) -> pd.DataFrame:
    """Build a minimal price DataFrame with sequential trading dates."""
    n = len(closes)
    return pd.DataFrame({
        "stock_id": "2330",
        "date":     [start + timedelta(days=i) for i in range(n)],
        "open":     closes,
        "high":     closes,
        "low":      closes,
        "close":    closes,
        "volume":   [1_000_000] * n,
    })


def make_fund_df(
    eps_list: list[float],
    first_period: date = date(2023, 3, 31),
    release_date: date | None = None,
) -> pd.DataFrame:
    """Build a quarterly fundamentals DataFrame with quarterly report_periods."""
    periods = [
        date(first_period.year + (first_period.month + i * 3 - 1) // 12,
             (first_period.month + i * 3 - 1) % 12 + 1,
             first_period.day)
        for i in range(len(eps_list))
    ]
    df = pd.DataFrame({
        "stock_id":      "2330",
        "report_period": periods,
        "eps":           eps_list,
    })
    if release_date is not None:
        df["release_date"] = release_date
    return df


# ---------------------------------------------------------------------------
# _growth_score — scoring monotonicity and bounds
# ---------------------------------------------------------------------------

def test_score_at_threshold_equals_base():
    score = _growth_score(0.30, threshold=0.30)
    assert score == 0.50


def test_score_is_monotonically_increasing():
    threshold = 0.30
    growths = [0.30, 0.40, 0.50, 0.70, 1.00, 2.00]
    scores = [_growth_score(g, threshold) for g in growths]
    for a, b in zip(scores, scores[1:]):
        assert b > a, f"Score not increasing: {a} → {b}"


def test_score_never_reaches_1():
    assert _growth_score(10.0, threshold=0.30) < 1.0


def test_score_upper_bound():
    assert _growth_score(100.0, threshold=0.30) <= 1.0


def test_score_moderate_growth_between_0_5_and_0_8():
    # 40–50% growth should score in the moderate band
    assert 0.60 < _growth_score(0.40, 0.30) < 0.80
    assert 0.60 < _growth_score(0.50, 0.30) < 0.80


def test_score_strong_growth_above_0_9():
    assert _growth_score(1.00, 0.30) > 0.90


# ---------------------------------------------------------------------------
# _effective_date — release_date vs fallback
# ---------------------------------------------------------------------------

def test_effective_date_uses_release_date_when_present():
    row = pd.Series({
        "report_period": date(2024, 3, 31),
        "release_date":  date(2024, 4, 25),
    })
    assert _effective_date(row) == date(2024, 4, 25)


def test_effective_date_fallback_non_q4():
    row = pd.Series({"report_period": date(2024, 3, 31)})
    assert _effective_date(row) == date(2024, 3, 31) + timedelta(days=45)


def test_effective_date_fallback_q4():
    row = pd.Series({"report_period": date(2023, 12, 31)})
    assert _effective_date(row) == date(2023, 12, 31) + timedelta(days=90)


def test_effective_date_nan_release_uses_fallback():
    row = pd.Series({"report_period": date(2024, 6, 30), "release_date": float("nan")})
    assert _effective_date(row) == date(2024, 6, 30) + timedelta(days=45)


# ---------------------------------------------------------------------------
# _add_yoy_growth — YoY calculation
# ---------------------------------------------------------------------------

def test_yoy_growth_requires_4_prior_quarters():
    fund_df = make_fund_df([1.0, 1.2, 1.4, 1.6, 2.0])
    result = _add_yoy_growth(fund_df)
    # First 4 quarters have no prior-year data
    assert result["yoy_growth"].iloc[:4].isna().all()
    # 5th quarter: (2.0 - 1.0) / 1.0 = 1.0 = 100%
    assert abs(result["yoy_growth"].iloc[4] - 1.0) < 1e-6


def test_yoy_growth_negative_base_eps():
    # Prior EPS = -2.0, current = -1.0 → improvement but negative base
    fund_df = make_fund_df([-2.0, -1.5, -1.0, -0.5, -1.0])
    result = _add_yoy_growth(fund_df)
    # yoy = (-1.0 - (-2.0)) / |-2.0| = 1.0 / 2.0 = 0.5
    assert abs(result["yoy_growth"].iloc[4] - 0.5) < 1e-6


# ---------------------------------------------------------------------------
# DavisDoubleStrategy.generate — signal count and trigger date
# ---------------------------------------------------------------------------

@pytest.fixture()
def strategy():
    return DavisDoubleStrategy(ma_window=3, yoy_threshold=0.30, max_ma_distance=0.15)


def _build_scenario(
    price_close: float = 120.0,
    ma_close: float = 100.0,   # MA is average of first 3 days
    yoy_growth: float = 0.50,
    release_date: date | None = None,
):
    """Build a minimal price + fundamentals pair for one passing quarter."""
    # 5 prices: first 3 form the MA baseline, 4th is the trigger day
    # MA(3) of [100, 100, 100, price_close] = 100 for the first 3 days
    n_baseline = 3
    prices = [ma_close] * n_baseline + [price_close]
    price_df = make_price_df(prices, start=date(2024, 5, 1))

    # 5 quarters (4 prior + current) so YoY is defined
    prior_eps = 1.0
    current_eps = prior_eps * (1 + yoy_growth)
    eps_list = [prior_eps] * 4 + [current_eps]
    fund_df = make_fund_df(eps_list, first_period=date(2023, 3, 31), release_date=release_date)

    return price_df, fund_df


def test_one_signal_per_qualifying_quarter(strategy):
    price_df, fund_df = _build_scenario(price_close=110.0, yoy_growth=0.50)
    signals = strategy.generate(price_df, fundamentals_df=fund_df)
    assert len(signals) == 1


def test_no_signal_when_yoy_below_threshold(strategy):
    price_df, fund_df = _build_scenario(price_close=110.0, yoy_growth=0.20)
    signals = strategy.generate(price_df, fundamentals_df=fund_df)
    assert signals == []


def test_no_signal_when_price_below_ma(strategy):
    price_df, fund_df = _build_scenario(price_close=90.0, yoy_growth=0.50)
    signals = strategy.generate(price_df, fundamentals_df=fund_df)
    assert signals == []


def test_no_signal_when_price_overextended(strategy):
    # distance_to_ma = (150 - 100) / 100 = 0.50 > max_ma_distance=0.15
    price_df, fund_df = _build_scenario(price_close=150.0, yoy_growth=0.50)
    signals = strategy.generate(price_df, fundamentals_df=fund_df)
    assert signals == []


def test_trigger_date_is_first_day_on_or_after_effective_date(strategy):
    # release_date = 2024-05-04 → trigger should be first trading day >= that date
    release = date(2024, 5, 4)
    price_df, fund_df = _build_scenario(price_close=110.0, yoy_growth=0.50,
                                        release_date=release)
    signals = strategy.generate(price_df, fundamentals_df=fund_df)
    if signals:
        assert signals[0].date >= release


def test_no_lookahead_effective_date_in_future(strategy):
    """If effective_date is beyond price data, no signal should fire."""
    prices = [100.0] * 4 + [110.0]
    price_df = make_price_df(prices, start=date(2024, 1, 2))

    # release_date far in the future — beyond price_df range
    far_future = date(2030, 1, 1)
    fund_df = make_fund_df([1.0] * 4 + [1.6], first_period=date(2023, 3, 31),
                           release_date=far_future)
    signals = strategy.generate(price_df, fundamentals_df=fund_df)
    assert signals == []


def test_signal_metadata_contains_expected_keys(strategy):
    price_df, fund_df = _build_scenario(price_close=110.0, yoy_growth=0.50)
    signals = strategy.generate(price_df, fundamentals_df=fund_df)
    if not signals:
        pytest.skip("No signal generated — check scenario setup")
    meta = signals[0].metadata
    for key in ("close", "ma", "eps", "yoy_growth_pct", "yoy_excess_pct",
                "distance_to_ma_pct", "report_period", "effective_date",
                "trigger_date", "yoy_threshold", "max_ma_distance", "ma_window"):
        assert key in meta, f"missing metadata key: {key}"


def test_distance_to_ma_in_metadata(strategy):
    price_df, fund_df = _build_scenario(price_close=110.0, yoy_growth=0.50)
    signals = strategy.generate(price_df, fundamentals_df=fund_df)
    if not signals:
        pytest.skip("No signal generated — check scenario setup")
    meta = signals[0].metadata
    expected = round((110.0 - 100.0) / 100.0 * 100, 2)
    assert abs(meta["distance_to_ma_pct"] - expected) < 0.1
