"""Run all applicable strategies on a single stock's prepared data.

Accepts the output of ``data.single_stock_loader.load_stock()`` and runs
whichever strategies have sufficient data.  Returns raw signals — one list
per strategy — and a flat signals DataFrame for easy inspection.

No aggregation or scoring is applied here; see ``strategies.combined`` for
the multi-strategy combined score.

Usage
-----
    from data.single_stock_loader import load_stock
    from analysis.single_stock_analysis import analyze_stock

    data    = load_stock("2330", start, end, token=TOKEN)
    result  = analyze_stock(data)

    print(result.signals_df)      # flat DataFrame of all signals
    print(result.summary())       # per-strategy signal counts
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd

from config import settings
from data.single_stock_loader import StockData
from signals.base import Signal
from strategies.davis_double import DavisDoubleStrategy
from strategies.margin_trend import MarginTrendStrategy
from strategies.price_volume import PriceVolumeStrategy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class AnalysisConfig:
    """Strategy parameters for single-stock analysis.

    All parameters mirror the corresponding strategy constructors.
    Defaults match the project-wide settings.
    """
    # PriceVolumeStrategy
    pv_price_window: int        = settings.MA_LONG_WINDOW
    pv_volume_window: int       = settings.VOLUME_SURGE_WINDOW
    pv_volume_surge_mult: float = settings.VOLUME_SURGE_MULTIPLIER
    pv_min_close: float         = settings.MIN_CLOSE_PRICE
    pv_max_breakout_pct: float  = 0.08
    pv_emit_weak_signals: bool  = True

    # MarginTrendStrategy
    mt_window: int              = 5
    mt_surge_threshold: float   = 0.05
    mt_unwind_threshold: float  = 0.03
    mt_min_abs_score: float     = 0.3
    mt_margin_weight: float     = 0.5
    mt_divergence_weight: float = 0.5

    # DavisDoubleStrategy
    dd_ma_window: int           = 60
    dd_yoy_threshold: float     = 0.30
    dd_max_ma_distance: float   = 0.15


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class AnalysisResult:
    """Output of analyze_stock().

    Attributes
    ----------
    stock_id        : Stock ticker.
    pv_signals      : Raw signals from PriceVolumeStrategy.
    mt_signals      : Raw signals from MarginTrendStrategy (empty if no margin data).
    dd_signals      : Raw signals from DavisDoubleStrategy (empty if no EPS data).
    signals_df      : Flat DataFrame of all signals with columns:
                      date, strategy, score, direction, signal_value, metadata.
    skipped         : Dict of strategy name → reason it was skipped.
    """
    stock_id:   str
    pv_signals: list[Signal]
    mt_signals: list[Signal]
    dd_signals: list[Signal]
    signals_df: pd.DataFrame
    skipped:    dict[str, str] = field(default_factory=dict)

    def summary(self) -> dict:
        """Per-strategy signal counts and skip reasons."""
        return {
            "stock_id":         self.stock_id,
            "price_volume":     len(self.pv_signals),
            "margin_trend":     len(self.mt_signals),
            "davis_double":     len(self.dd_signals),
            "total":            len(self.signals_df),
            "skipped":          self.skipped,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_stock(
    data:   StockData,
    config: Optional[AnalysisConfig] = None,
) -> AnalysisResult:
    """Run all applicable strategies on prepared single-stock data.

    Strategies are skipped gracefully when required data is absent:
    - ``margin_trend`` requires ``margin_purchase_balance`` to be non-empty.
    - ``davis_double`` requires ``eps`` to be non-empty.

    Parameters
    ----------
    data   : Output of ``load_stock()``.
    config : AnalysisConfig. Defaults to project-wide settings.

    Returns
    -------
    AnalysisResult with per-strategy signal lists and a combined signals_df.
    """
    if config is None:
        config = AnalysisConfig()

    skipped: dict[str, str] = {}
    pv_signals: list[Signal] = []
    mt_signals: list[Signal] = []
    dd_signals: list[Signal] = []

    if data.daily.empty:
        return AnalysisResult(
            stock_id   = data.stock_id,
            pv_signals = [],
            mt_signals = [],
            dd_signals = [],
            signals_df = _empty_signals_df(),
            skipped    = {"all": "no price data available"},
        )

    # Build the price DataFrame that strategies expect
    price_df = _build_price_df(data)

    # ── PriceVolumeStrategy ────────────────────────────────────────────────
    try:
        pv = PriceVolumeStrategy(
            price_window      = config.pv_price_window,
            volume_window     = config.pv_volume_window,
            volume_surge_mult = config.pv_volume_surge_mult,
            min_close         = config.pv_min_close,
            max_breakout_pct  = config.pv_max_breakout_pct,
            emit_weak_signals = config.pv_emit_weak_signals,
        )
        pv_signals = pv.generate(price_df)
    except Exception as exc:
        logger.warning("price_volume failed for %s: %s", data.stock_id, exc)
        skipped["price_volume"] = str(exc)

    # ── MarginTrendStrategy ────────────────────────────────────────────────
    margin_df = _build_margin_df(data)
    if margin_df is None:
        skipped["margin_trend"] = "margin_purchase_balance not available"
    else:
        try:
            mt = MarginTrendStrategy(
                window             = config.mt_window,
                surge_threshold    = config.mt_surge_threshold,
                unwind_threshold   = config.mt_unwind_threshold,
                min_abs_score      = config.mt_min_abs_score,
                margin_weight      = config.mt_margin_weight,
                divergence_weight  = config.mt_divergence_weight,
            )
            mt_signals = mt.generate(price_df, margin_df=margin_df)
        except Exception as exc:
            logger.warning("margin_trend failed for %s: %s", data.stock_id, exc)
            skipped["margin_trend"] = str(exc)

    # ── DavisDoubleStrategy ────────────────────────────────────────────────
    fund_df = _build_fundamentals_df(data)
    if fund_df is None:
        skipped["davis_double"] = "EPS data not available"
    else:
        try:
            dd = DavisDoubleStrategy(
                ma_window       = config.dd_ma_window,
                yoy_threshold   = config.dd_yoy_threshold,
                max_ma_distance = config.dd_max_ma_distance,
            )
            dd_signals = dd.generate(price_df, fundamentals_df=fund_df)
        except Exception as exc:
            logger.warning("davis_double failed for %s: %s", data.stock_id, exc)
            skipped["davis_double"] = str(exc)

    signals_df = _to_signals_df(pv_signals + mt_signals + dd_signals)

    return AnalysisResult(
        stock_id   = data.stock_id,
        pv_signals = pv_signals,
        mt_signals = mt_signals,
        dd_signals = dd_signals,
        signals_df = signals_df,
        skipped    = skipped,
    )


# ---------------------------------------------------------------------------
# Internal helpers — data preparation
# ---------------------------------------------------------------------------

def _build_price_df(data: StockData) -> pd.DataFrame:
    """Extract the price DataFrame that strategies expect."""
    df = data.daily[["date", "close", "volume"]].copy()
    df["stock_id"] = data.stock_id
    df["date"]     = pd.to_datetime(df["date"])
    # Strategies also use 'high' and 'open'; approximate with close if absent
    if "high" not in df.columns:
        df["high"] = df["close"]
    if "open" not in df.columns:
        df["open"] = df["close"]
    if "low" not in df.columns:
        df["low"] = df["close"]
    return df[["stock_id", "date", "open", "high", "low", "close", "volume"]]


def _build_margin_df(data: StockData) -> Optional[pd.DataFrame]:
    """Return a margin DataFrame if margin data is present, else None."""
    col = "margin_purchase_balance"
    if col not in data.daily.columns:
        return None
    valid = data.daily[data.daily[col].notna()]
    if valid.empty:
        return None
    df = data.daily[["date", col]].copy()
    df["stock_id"] = data.stock_id
    df["date"]     = pd.to_datetime(df["date"])
    return df[["stock_id", "date", col]]


def _build_fundamentals_df(data: StockData) -> Optional[pd.DataFrame]:
    """Return a fundamentals DataFrame if EPS data is present, else None.

    Reconstructs quarterly rows from the forward-filled daily EPS column by
    keeping the first day each EPS value appears (i.e. the effective date).
    """
    if "eps" not in data.daily.columns:
        return None
    daily = data.daily[data.daily["eps"].notna()].copy()
    if daily.empty:
        return None

    # Each new EPS value marks the start of a quarter's forward-fill window
    eps_changed = daily["eps"].ne(daily["eps"].shift())
    quarterly   = daily[eps_changed][["date", "eps"]].copy()
    if quarterly.empty:
        return None

    quarterly["stock_id"]      = data.stock_id
    quarterly["report_period"] = quarterly["date"]   # best approximation
    quarterly["release_date"]  = quarterly["date"]   # already the effective date
    return quarterly[["stock_id", "report_period", "eps", "release_date"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Internal helpers — signal formatting
# ---------------------------------------------------------------------------

def _to_signals_df(signals: list[Signal]) -> pd.DataFrame:
    """Convert a list of Signal objects to a flat inspection DataFrame."""
    if not signals:
        return _empty_signals_df()

    rows = []
    for s in signals:
        rows.append({
            "date":         s.date,
            "strategy":     s.signal_name,
            "score":        s.score,
            "direction":    s.direction.value if hasattr(s.direction, "value") else str(s.direction),
            "signal_value": s.signal_value,
            "metadata":     s.metadata or {},
        })

    return (
        pd.DataFrame(rows)
        .sort_values(["date", "strategy"])
        .reset_index(drop=True)
    )


def _empty_signals_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["date", "strategy", "score", "direction", "signal_value", "metadata"])
