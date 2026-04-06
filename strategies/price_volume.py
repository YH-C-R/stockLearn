import pandas as pd

from config import settings
from signals.base import Signal, make_signal
from strategies.base import BaseStrategy

_REQUIRED_COLUMNS = ["stock_id", "date", "close", "high", "volume"]


class PriceVolumeStrategy(BaseStrategy):
    """Price-breakout + volume-expansion strategy.

    Signal conditions (all must be true):
      1. close > rolling N-day high  (price breakout)
      2. breakout_pct <= max_breakout_pct  (not overextended)
      3. volume >= surge_mult × avg_volume  OR  emit_weak_signals=True

    Signal frequency:
      Only the FIRST day of a new breakout emits a signal.
      Subsequent days where close is still above the rolling high are suppressed.
      A new signal can fire once price pulls back below the rolling high and then
      breaks out again.

    Score scale:
      +1.0  volume ≥ 2× surge threshold
      +0.8  volume ≥ surge threshold
      +0.4  breakout only, no volume confirmation (only when emit_weak_signals=True)

    Parameters
    ----------
    price_window      : Lookback for rolling high.
    volume_window     : Lookback for rolling average volume.
    volume_surge_mult : Volume multiple to confirm a breakout.
    min_close         : Skip rows with close below this (penny stock filter).
    max_breakout_pct  : Skip if close/rolling_high - 1 exceeds this (overextended filter).
    emit_weak_signals : If False, suppress breakouts without volume confirmation.
    """

    name = "price_volume"

    def __init__(
        self,
        price_window: int          = settings.MA_LONG_WINDOW,
        volume_window: int         = settings.VOLUME_SURGE_WINDOW,
        volume_surge_mult: float   = settings.VOLUME_SURGE_MULTIPLIER,
        min_close: float           = settings.MIN_CLOSE_PRICE,
        max_breakout_pct: float    = 0.08,
        emit_weak_signals: bool    = True,
    ) -> None:
        self.price_window      = price_window
        self.volume_window     = volume_window
        self.volume_surge_mult = volume_surge_mult
        self.min_close         = min_close
        self.max_breakout_pct  = max_breakout_pct
        self.emit_weak_signals = emit_weak_signals

    def generate(self, price_df: pd.DataFrame, **kwargs: pd.DataFrame) -> list[Signal]:
        """Return one signal per new breakout event per stock."""
        self.validate_columns(price_df, _REQUIRED_COLUMNS)

        df = price_df.copy()
        df = df.sort_values(["stock_id", "date"]).reset_index(drop=True)
        df = df[df["close"] >= self.min_close]

        df["rolling_high"] = df.groupby("stock_id")["high"].transform(
            lambda x: x.shift(1).rolling(self.price_window).max()
        )
        df["avg_volume"] = df.groupby("stock_id")["volume"].transform(
            lambda x: x.shift(1).rolling(self.volume_window).mean()
        )

        # Flag each row as in-breakout (close > rolling_high)
        df["in_breakout"] = df["close"] > df["rolling_high"]

        # First day of a new breakout: in_breakout=True AND previous row was False
        # Use groupby + shift to compare within each stock
        df["prev_in_breakout"] = df.groupby("stock_id")["in_breakout"].transform(
            lambda x: x.shift(1).fillna(False)
        )
        df["new_breakout"] = df["in_breakout"] & ~df["prev_in_breakout"]

        signals: list[Signal] = []
        for row in df.itertuples(index=False):
            if pd.isna(row.rolling_high) or pd.isna(row.avg_volume):
                continue
            if not row.new_breakout:
                continue

            breakout_pct  = (row.close / row.rolling_high) - 1.0
            if breakout_pct > self.max_breakout_pct:
                continue  # overextended — skip

            volume_ratio  = row.volume / row.avg_volume if row.avg_volume > 0 else 0.0
            score, label  = self._score(volume_ratio)

            if score == 0.4 and not self.emit_weak_signals:
                continue  # weak breakout suppressed by config

            volume_excess_pct = (volume_ratio - 1.0) * 100.0

            signals.append(make_signal(
                stock_id=row.stock_id,
                date=row.date,
                signal_name=self.name,
                signal_value=round(row.close, 2),
                score=score,
                metadata={
                    "rolling_high":       round(row.rolling_high, 2),
                    "avg_volume":         int(row.avg_volume),
                    "volume_ratio":       round(volume_ratio, 2),
                    "volume_excess_pct":  round(volume_excess_pct, 2),
                    "breakout_pct":       round(breakout_pct * 100, 2),
                    "confirmation":       label,
                    "price_window":       self.price_window,
                    "volume_window":      self.volume_window,
                    "volume_surge_mult":  self.volume_surge_mult,
                },
            ))

        return signals

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _score(self, volume_ratio: float) -> tuple[float, str]:
        double_surge = self.volume_surge_mult * 2
        if volume_ratio >= double_surge:
            return 1.0, "strong_surge"
        if volume_ratio >= self.volume_surge_mult:
            return 0.8, "surge"
        return 0.4, "no_volume_confirmation"
