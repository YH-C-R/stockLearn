"""Reusable performance metric functions for backtesting.

All public functions operate on a ``pd.Series`` of per-trade return
percentages (e.g. ``+5.0`` means +5%).  They are stateless and
side-effect-free so they can be imported by any backtesting module.

Two tiers of API
----------------
Individual functions (``win_rate``, ``avg_return``, ``cumulative_return``,
``equity_curve``, ``max_drawdown``):
    - Strict: raise ``ValueError`` on empty input (except ``equity_curve``
      and ``max_drawdown``, which return safe zero-values for empty input).
    - Suitable for callers that already know they have trades.

Aggregate wrapper (``compute_trade_metrics``):
    - Safe: accepts empty input and returns a zero-value dict.
    - Normalises any array-like to ``pd.Series`` before calling
      individual functions.
    - Intended as the primary entry point for engine.py and portfolio.py.

Usage
-----
    from backtesting.metrics import compute_trade_metrics, equity_curve

    metrics = compute_trade_metrics(trades_df["return_pct"])
    curve   = equity_curve(trades_df["return_pct"])
"""

from __future__ import annotations

import pandas as pd


# ---------------------------------------------------------------------------
# Individual metric functions  (strict — raise on empty where noted)
# ---------------------------------------------------------------------------

def win_rate(returns_pct: pd.Series) -> float:
    """Fraction of trades with a strictly positive return, as a percentage.

    Parameters
    ----------
    returns_pct : Per-trade returns in percent (e.g. ``3.5`` means +3.5%).
                  Must be non-empty.

    Returns
    -------
    float in [0.0, 100.0], rounded to 2 decimal places.

    Raises
    ------
    ValueError : If ``returns_pct`` is empty.
    """
    _require_non_empty(returns_pct, "win_rate")
    return round(float((returns_pct > 0).sum() / len(returns_pct) * 100), 2)


def avg_return(returns_pct: pd.Series) -> float:
    """Arithmetic mean of per-trade returns.

    Parameters
    ----------
    returns_pct : Per-trade returns in percent.  Must be non-empty.

    Returns
    -------
    float, rounded to 4 decimal places.

    Raises
    ------
    ValueError : If ``returns_pct`` is empty.
    """
    _require_non_empty(returns_pct, "avg_return")
    return round(float(returns_pct.mean()), 4)


def cumulative_return(returns_pct: pd.Series) -> float:
    """Compounded cumulative return across all trades.

    Computes ``(∏(1 + rᵢ/100) − 1) × 100``, where each ``rᵢ`` is a
    per-trade return in percent.  Assumes sequential reinvestment.

    Parameters
    ----------
    returns_pct : Per-trade returns in percent.  Must be non-empty.

    Returns
    -------
    float in percent, rounded to 4 decimal places.
    e.g. ``+10.5`` means the portfolio grew by 10.5% overall.

    Raises
    ------
    ValueError : If ``returns_pct`` is empty.
    """
    _require_non_empty(returns_pct, "cumulative_return")
    result = ((1 + returns_pct / 100).prod() - 1) * 100
    return round(float(result), 4)


def equity_curve(returns_pct: pd.Series) -> pd.Series:
    """Normalised equity curve as a cumulative product of (1 + rᵢ/100).

    The first value equals ``1 + r₀/100``; subsequent values compound
    forward.  Start-of-period capital is implicitly 1.0.

    Parameters
    ----------
    returns_pct : Per-trade returns in percent, in chronological order.

    Returns
    -------
    ``pd.Series`` with the same index as ``returns_pct``.
    Returns an empty ``pd.Series`` (dtype float) if input is empty.
    """
    if returns_pct.empty:
        return pd.Series(dtype=float)
    return (1 + returns_pct / 100).cumprod()


def max_drawdown(returns_pct: pd.Series) -> float:
    """Maximum peak-to-trough drawdown of the equity curve, in percent.

    Measures the largest percentage decline from any running peak to any
    subsequent trough.  An initial implicit peak of 1.0 is prepended so
    that a loss on the very first trade is captured correctly.

    Parameters
    ----------
    returns_pct : Per-trade returns in percent, in chronological order.

    Returns
    -------
    float <= 0.0, rounded to 4 decimal places.
    e.g. ``-15.3`` means the portfolio fell 15.3% from its worst peak.
    Returns ``0.0`` for empty input or when the curve never declines.
    """
    if returns_pct.empty:
        return 0.0
    curve = pd.concat(
        [pd.Series([1.0]), equity_curve(returns_pct)],
        ignore_index=True,
    )
    peak = curve.cummax()
    dd   = (curve - peak) / peak * 100
    return round(float(dd.min()), 4)


# ---------------------------------------------------------------------------
# Aggregate wrapper  (safe — never raises, normalises input)
# ---------------------------------------------------------------------------

def compute_trade_metrics(returns_pct: pd.Series | list | None) -> dict:
    """Compute all standard metrics and return them as a single dict.

    This is the recommended entry point for ``engine.py`` and
    ``portfolio.py``.  Unlike the individual functions, it:

    - Accepts any array-like (``list``, ``np.ndarray``, ``pd.Series``)
      and normalises it to a ``pd.Series[float]`` before processing.
    - Returns a zero-value dict instead of raising on empty input.

    Parameters
    ----------
    returns_pct : Per-trade returns in percent.  May be empty or ``None``.

    Returns
    -------
    dict with keys:
        ``num_trades``            : int
        ``win_rate_pct``          : float
        ``avg_return_pct``        : float
        ``cumulative_return_pct`` : float
        ``max_drawdown_pct``      : float
    """
    series = _to_series(returns_pct)
    if series.empty:
        return _empty_metrics()

    return {
        "num_trades":            len(series),
        "win_rate_pct":          win_rate(series),
        "avg_return_pct":        avg_return(series),
        "cumulative_return_pct": cumulative_return(series),
        "max_drawdown_pct":      max_drawdown(series),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _to_series(data: pd.Series | list | None) -> pd.Series:
    """Coerce *data* to a float ``pd.Series``.  ``None`` → empty Series."""
    if data is None:
        return pd.Series(dtype=float)
    if isinstance(data, pd.Series):
        return data.astype(float).reset_index(drop=True)
    return pd.Series(data, dtype=float)


def _require_non_empty(series: pd.Series, fn_name: str) -> None:
    """Raise ``ValueError`` if *series* is empty."""
    if series.empty:
        raise ValueError(f"{fn_name}() requires a non-empty Series")


def _empty_metrics() -> dict:
    return {
        "num_trades":            0,
        "win_rate_pct":          0.0,
        "avg_return_pct":        0.0,
        "cumulative_return_pct": 0.0,
        "max_drawdown_pct":      0.0,
    }
