import pandas as pd

from config import settings
from signals.base import Signal, make_signal
from strategies.base import BaseStrategy

_REQUIRED_COLUMNS = ["stock_id", "date", "close", "high", "volume"]


class PriceVolumeStrategy(BaseStrategy):
    """Price-breakout + volume-expansion strategy.

    Fires a bullish signal when both conditions are true on the same day:
      1. Close breaks above the rolling N-day high (price breakout).
      2. Volume exceeds M× the rolling N-day average (volume confirmation).

    A breakout without volume confirmation produces a weaker signal (score 0.4).
    A breakout confirmed by volume produces a strong signal (score 0.8 or 1.0).

    Score scale
    -----------
    +1.0  breakout + volume surge ≥ 2× threshold
    +0.8  breakout + volume surge ≥ threshold
    +0.4  breakout only (no volume confirmation)
     0.0  no breakout (row skipped — not emitted)

    Parameters
    ----------
    price_window          : Lookback for rolling high (default: MA_LONG_WINDOW).
    volume_window         : Lookback for rolling average volume (default: VOLUME_SURGE_WINDOW).
    volume_surge_mult     : Volume multiple to confirm a breakout (default: VOLUME_SURGE_MULTIPLIER).
    min_close             : Rows with close below this are ignored (default: MIN_CLOSE_PRICE).
    """

    name = "price_volume"

    def __init__(
        self,
        price_window: int = settings.MA_LONG_WINDOW,
        volume_window: int = settings.VOLUME_SURGE_WINDOW,
        volume_surge_mult: float = settings.VOLUME_SURGE_MULTIPLIER,
        min_close: float = settings.MIN_CLOSE_PRICE,
    ) -> None:
        self.price_window = price_window
        self.volume_window = volume_window
        self.volume_surge_mult = volume_surge_mult
        self.min_close = min_close

    def generate(self, price_df: pd.DataFrame, **kwargs: pd.DataFrame) -> list[Signal]:
        """Return bullish signals for days where price breaks out on volume."""
        self.validate_columns(price_df, _REQUIRED_COLUMNS)

        df = price_df.copy()
        df = df.sort_values(["stock_id", "date"]).reset_index(drop=True)
        df = df[df["close"] >= self.min_close]

        # Compute indicators per stock using transform (preserves DataFrame structure)
        df["rolling_high"] = df.groupby("stock_id")["high"].transform(
            lambda x: x.shift(1).rolling(self.price_window).max()
        )
        df["avg_volume"] = df.groupby("stock_id")["volume"].transform(
            lambda x: x.shift(1).rolling(self.volume_window).mean()
        )

        signals: list[Signal] = []
        for row in df.itertuples(index=False):
            if pd.isna(row.rolling_high) or pd.isna(row.avg_volume):
                continue  # insufficient history

            breakout = row.close > row.rolling_high
            if not breakout:
                continue

            volume_ratio = row.volume / row.avg_volume if row.avg_volume > 0 else 0.0
            score, label = self._score(volume_ratio)

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
        """Map volume ratio to a normalised score and a human-readable label."""
        double_surge = self.volume_surge_mult * 2
        if volume_ratio >= double_surge:
            return 1.0, "strong_surge"
        if volume_ratio >= self.volume_surge_mult:
            return 0.8, "surge"
        return 0.4, "no_volume_confirmation"
