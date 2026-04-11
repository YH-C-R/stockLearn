"""Unit tests for backtesting/metrics.py."""

import pandas as pd
import pytest

from backtesting.metrics import (
    avg_return,
    compute_trade_metrics,
    cumulative_return,
    equity_curve,
    max_drawdown,
    win_rate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def s(*values) -> pd.Series:
    """Shorthand: build a float Series from positional args."""
    return pd.Series(values, dtype=float)


# ---------------------------------------------------------------------------
# win_rate
# ---------------------------------------------------------------------------

def test_win_rate_all_winners():
    assert win_rate(s(1.0, 2.0, 3.0)) == 100.0


def test_win_rate_all_losers():
    assert win_rate(s(-1.0, -2.0, -3.0)) == 0.0


def test_win_rate_mixed():
    # 2 winners out of 4 → 50%
    assert win_rate(s(5.0, -3.0, 2.0, -1.0)) == 50.0


def test_win_rate_zero_return_not_counted_as_win():
    # 0.0 is not > 0, so it does not count as a win
    assert win_rate(s(0.0, 0.0)) == 0.0


def test_win_rate_empty_raises():
    with pytest.raises(ValueError, match="non-empty"):
        win_rate(pd.Series(dtype=float))


# ---------------------------------------------------------------------------
# cumulative_return
# ---------------------------------------------------------------------------

def test_cumulative_return_single_trade():
    # +10% → cumulative = 10%
    assert cumulative_return(s(10.0)) == pytest.approx(10.0, rel=1e-4)


def test_cumulative_return_two_trades_compound():
    # +10% then +10%: 1.1 * 1.1 - 1 = 0.21 → 21%
    result = cumulative_return(s(10.0, 10.0))
    assert result == pytest.approx(21.0, rel=1e-3)


def test_cumulative_return_gain_then_loss():
    # +50% then -50%: 1.5 * 0.5 - 1 = -0.25 → -25%
    result = cumulative_return(s(50.0, -50.0))
    assert result == pytest.approx(-25.0, rel=1e-4)


def test_cumulative_return_all_flat():
    assert cumulative_return(s(0.0, 0.0, 0.0)) == pytest.approx(0.0, abs=1e-6)


def test_cumulative_return_empty_raises():
    with pytest.raises(ValueError, match="non-empty"):
        cumulative_return(pd.Series(dtype=float))


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------

def test_max_drawdown_no_loss():
    # Monotonically increasing equity → no drawdown
    assert max_drawdown(s(5.0, 5.0, 5.0)) == 0.0


def test_max_drawdown_single_loss():
    # equity: 1.0 → 0.9 → drawdown = -10%
    result = max_drawdown(s(-10.0))
    assert result == pytest.approx(-10.0, rel=1e-4)


def test_max_drawdown_peak_then_trough():
    # equity: 1.1, 1.21, 1.089 (−10% from peak of 1.21)
    result = max_drawdown(s(10.0, 10.0, -10.0))
    assert result == pytest.approx(-10.0, rel=1e-3)


def test_max_drawdown_recovers_after_loss():
    # equity: 1.1 → 0.99 (−10%) → 1.188 (recovers)
    # drawdown is still ~−10% at the trough
    result = max_drawdown(s(10.0, -10.0, 20.0))
    assert result < 0.0
    assert result >= -11.0  # bounded — no catastrophic drawdown


def test_max_drawdown_empty_returns_zero():
    assert max_drawdown(pd.Series(dtype=float)) == 0.0


# ---------------------------------------------------------------------------
# equity_curve
# ---------------------------------------------------------------------------

def test_equity_curve_starts_at_first_trade_factor():
    curve = equity_curve(s(10.0))   # 1 trade +10% → factor 1.1
    assert curve.iloc[0] == pytest.approx(1.1, rel=1e-6)


def test_equity_curve_monotone_on_all_gains():
    curve = equity_curve(s(10.0, 20.0, 5.0))
    assert list(curve) == sorted(curve)   # strictly increasing


def test_equity_curve_empty_returns_empty():
    result = equity_curve(pd.Series(dtype=float))
    assert result.empty


# ---------------------------------------------------------------------------
# compute_trade_metrics (composite)
# ---------------------------------------------------------------------------

def test_compute_trade_metrics_known_values():
    # 3 trades: +10%, -5%, +20%
    metrics = compute_trade_metrics(s(10.0, -5.0, 20.0))
    assert metrics["num_trades"] == 3
    assert metrics["win_rate_pct"] == pytest.approx(66.67, rel=1e-2)
    assert metrics["avg_return_pct"] == pytest.approx(25.0 / 3, rel=1e-3)
    # compound: 1.1 * 0.95 * 1.2 = 1.254 → +25.4%
    assert metrics["cumulative_return_pct"] == pytest.approx(25.4, rel=1e-2)
    assert metrics["max_drawdown_pct"] <= 0.0


def test_compute_trade_metrics_empty_returns_zeros():
    metrics = compute_trade_metrics(pd.Series(dtype=float))
    assert metrics["num_trades"] == 0
    assert metrics["win_rate_pct"] == 0.0
    assert metrics["avg_return_pct"] == 0.0
    assert metrics["cumulative_return_pct"] == 0.0
    assert metrics["max_drawdown_pct"] == 0.0


def test_compute_trade_metrics_keys_complete():
    metrics = compute_trade_metrics(s(1.0))
    expected_keys = {
        "num_trades", "win_rate_pct", "avg_return_pct",
        "cumulative_return_pct", "max_drawdown_pct",
    }
    assert set(metrics.keys()) == expected_keys
