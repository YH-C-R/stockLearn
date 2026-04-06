import pandas as pd

from signals.base import Signal, make_signal
from strategies.base import BaseStrategy

_REQUIRED_PRICE_COLS  = ["stock_id", "date", "close"]
_REQUIRED_MARGIN_COLS = ["stock_id", "date", "margin_purchase_balance", "short_sale_balance"]


class MarginTrendStrategy(BaseStrategy):
    """Price-vs-margin divergence strategy.

    Combines two independent sub-signals, each scored in [-1, 1], then
    averages them into a final score.

    Sub-signal 1 — Margin financing trend (margin_signal)
    ------------------------------------------------------
    Compares the N-day percentage change in margin_purchase_balance against
    a threshold.

      margin_change > +surge_threshold  →  crowded long / over-leveraged
                                           (bearish: retail piling in on margin)
      margin_change < -unwind_threshold →  margin being actively unwound
                                           (bullish: forced sellers clearing out)
      otherwise                          →  neutral

    Sub-signal 2 — Price vs margin divergence (divergence_signal)
    --------------------------------------------------------------
    Compares the N-day price return with the direction of margin balance change.
    Healthy rallies see price rise with FLAT or FALLING margin (smart money leads).
    Unhealthy rallies see price rise with RISING margin (retail chases with leverage).

      price up   + margin down  →  bullish  (+1.0)
      price down + margin up    →  bearish  (-1.0)
      price up   + margin up    →  weakly bearish (-0.4, over-leveraged rally)
      price down + margin down  →  weakly bullish (+0.4, margin unwinding = clean-up)
      otherwise                 →  neutral (0.0)

    Final score = mean(margin_signal, divergence_signal), clamped to [-1, 1].
    Only rows where |final_score| >= min_abs_score emit a Signal.

    Parameters
    ----------
    window            : Lookback window (days) for pct-change calculations.
    surge_threshold   : Margin balance pct-change above this → crowded (bearish).
    unwind_threshold  : Margin balance pct-change below negative this → bullish.
    min_abs_score     : Minimum |score| to emit a signal (filters weak signals).
    """

    name = "margin_trend"

    def __init__(
        self,
        window: int            = 5,
        surge_threshold: float = 0.05,   # +5 % margin balance growth → crowded
        unwind_threshold: float = 0.03,  # -3 % margin balance shrink → clean
        min_abs_score: float   = 0.3,
    ) -> None:
        self.window           = window
        self.surge_threshold  = surge_threshold
        self.unwind_threshold = unwind_threshold
        self.min_abs_score    = min_abs_score

    def generate(
        self,
        price_df: pd.DataFrame,
        *,
        margin_df: pd.DataFrame,
        **kwargs: pd.DataFrame,
    ) -> list[Signal]:
        """Return margin-trend signals by merging price and margin data.

        Parameters
        ----------
        price_df  : Daily OHLCV DataFrame (stock_id, date, close, …).
        margin_df : Daily margin DataFrame from fetch_margin_data()
                    (stock_id, date, margin_purchase_balance, short_sale_balance).
        """
        self.validate_columns(price_df,  _REQUIRED_PRICE_COLS,  "price_df")
        self.validate_columns(margin_df, _REQUIRED_MARGIN_COLS, "margin_df")

        price_df  = price_df.copy()
        margin_df = margin_df.copy()

        price_df["date"]  = pd.to_datetime(price_df["date"]).dt.date
        margin_df["date"] = pd.to_datetime(margin_df["date"]).dt.date

        df = pd.merge(
            price_df[["stock_id", "date", "close"]],
            margin_df[["stock_id", "date", "margin_purchase_balance", "short_sale_balance"]],
            on=["stock_id", "date"],
            how="inner",
        )

        if df.empty:
            return []

        df = df.sort_values(["stock_id", "date"]).reset_index(drop=True)
        df["price_change"]  = df.groupby("stock_id")["close"].transform(
            lambda x: x.pct_change(self.window)
        )
        df["margin_change"] = df.groupby("stock_id")["margin_purchase_balance"].transform(
            lambda x: x.pct_change(self.window)
        )

        signals: list[Signal] = []
        for row in df.itertuples(index=False):
            if pd.isna(row.margin_change) or pd.isna(row.price_change):
                continue

            margin_score     = self._margin_signal(row.margin_change)
            diverge_score    = self._divergence_signal(row.price_change, row.margin_change)
            final_score      = round((margin_score + diverge_score) / 2, 4)

            if abs(final_score) < self.min_abs_score:
                continue

            signals.append(make_signal(
                stock_id=row.stock_id,
                date=row.date,
                signal_name=self.name,
                signal_value=round(row.margin_purchase_balance, 0),
                score=max(-1.0, min(1.0, final_score)),
                metadata={
                    "close":                    round(row.close, 2),
                    "price_change_pct":         round(row.price_change * 100, 4),
                    "margin_change_pct":        round(row.margin_change * 100, 4),
                    "margin_purchase_balance":  int(row.margin_purchase_balance),
                    "short_sale_balance":       int(row.short_sale_balance),
                    "margin_signal":            margin_score,
                    "divergence_signal":        diverge_score,
                    "window":                   self.window,
                },
            ))

        return signals

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _margin_signal(self, margin_change: float) -> float:
        """Score based solely on the direction and magnitude of margin growth."""
        if margin_change > self.surge_threshold:
            return -1.0   # over-leveraged rally — bearish
        if margin_change < -self.unwind_threshold:
            return +1.0   # margin unwinding — bullish
        return 0.0

    def _divergence_signal(self, price_change: float, margin_change: float) -> float:
        """Score based on the relationship between price direction and margin direction."""
        price_up   = price_change  > 0
        price_down = price_change  < 0
        margin_up  = margin_change > 0
        margin_dn  = margin_change < 0

        if price_up   and margin_dn:  return +1.0   # healthy rally
        if price_down and margin_up:  return -1.0   # price falling, more leverage — dangerous
        if price_up   and margin_up:  return -0.4   # rally on leverage — weaker
        if price_down and margin_dn:  return +0.4   # price dips but margin cleans up — base-build
        return 0.0
