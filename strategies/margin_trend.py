import pandas as pd

from signals.base import Signal, make_signal
from strategies.base import BaseStrategy

_REQUIRED_PRICE_COLS  = ["stock_id", "date", "close"]
_REQUIRED_MARGIN_COLS = ["stock_id", "date", "margin_purchase_balance"]

# short_sale_balance is retained in metadata when present but is not required
# for signal generation. Include it in a future sub-signal when ready.
_OPTIONAL_MARGIN_COLS = ["short_sale_balance"]


class MarginTrendStrategy(BaseStrategy):
    """Price-vs-margin divergence strategy.

    Combines two independent sub-signals into a weighted final score.

    Sub-signal 1 — Margin financing trend (margin_signal)
    ------------------------------------------------------
    Compares the N-day pct-change in margin_purchase_balance against thresholds.

      margin_change > +surge_threshold   →  -1.0  (retail crowding in — bearish)
      margin_change < -unwind_threshold  →  +1.0  (margin unwinding — bullish)
      otherwise                          →   0.0  (neutral)

    Sub-signal 2 — Price vs margin divergence (divergence_signal)
    --------------------------------------------------------------
    Compares N-day price direction with margin direction.

      price up   + margin down  →  +1.0   healthy rally
      price down + margin up    →  -1.0   dangerous — price falling on rising leverage
      price up   + margin up    →  -0.4   leveraged rally — weaker
      price down + margin down  →  +0.4   base-building — margin cleaning up
      otherwise                 →   0.0   neutral

    Final score = margin_weight * margin_signal + divergence_weight * divergence_signal
    Normalised to [-1, 1]. Only emitted when |score| >= min_abs_score.

    # Future extension point
    # ----------------------
    # A cooldown / dedup filter can be added here before appending to signals:
    #   last_signal_date = last_signal_dates.get(row.stock_id)
    #   if last_signal_date and (row.date - last_signal_date).days < cooldown_days:
    #       continue
    # Intentionally omitted for now to keep the logic simple.

    Parameters
    ----------
    window             : Lookback window (days) for pct-change calculations.
    surge_threshold    : Margin pct-change above this → bearish (-1.0).
    unwind_threshold   : Margin pct-change below negative this → bullish (+1.0).
    min_abs_score      : Minimum |score| required to emit a signal.
    margin_weight      : Weight applied to margin_signal in the final score.
    divergence_weight  : Weight applied to divergence_signal in the final score.
    """

    name = "margin_trend"

    def __init__(
        self,
        window: int              = 5,
        surge_threshold: float   = 0.05,
        unwind_threshold: float  = 0.03,
        min_abs_score: float     = 0.5,
        margin_weight: float     = 0.5,
        divergence_weight: float = 0.5,
    ) -> None:
        if abs(margin_weight + divergence_weight) < 1e-9:
            raise ValueError("margin_weight + divergence_weight must not sum to zero")
        self.window            = window
        self.surge_threshold   = surge_threshold
        self.unwind_threshold  = unwind_threshold
        self.min_abs_score     = min_abs_score
        self.margin_weight     = margin_weight
        self.divergence_weight = divergence_weight

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
        margin_df : Daily margin DataFrame (stock_id, date, margin_purchase_balance, …).
        """
        self.validate_columns(price_df,  _REQUIRED_PRICE_COLS,  "price_df")
        self.validate_columns(margin_df, _REQUIRED_MARGIN_COLS, "margin_df")

        price_df  = price_df.copy()
        margin_df = margin_df.copy()

        price_df["date"]  = pd.to_datetime(price_df["date"]).dt.date
        margin_df["date"] = pd.to_datetime(margin_df["date"]).dt.date

        # Carry short_sale_balance into metadata if the column exists
        margin_cols = ["stock_id", "date", "margin_purchase_balance"]
        if "short_sale_balance" in margin_df.columns:
            margin_cols.append("short_sale_balance")

        df = pd.merge(
            price_df[["stock_id", "date", "close"]],
            margin_df[margin_cols],
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

        total_weight = self.margin_weight + self.divergence_weight

        signals: list[Signal] = []
        for row in df.itertuples(index=False):
            if pd.isna(row.margin_change) or pd.isna(row.price_change):
                continue

            margin_score   = self._margin_signal(row.margin_change)
            diverge_score  = self._divergence_signal(row.price_change, row.margin_change)
            raw_score      = (self.margin_weight * margin_score
                              + self.divergence_weight * diverge_score)
            final_score    = round(raw_score / total_weight, 4)

            if abs(final_score) < self.min_abs_score:
                continue

            final_score = max(-1.0, min(1.0, final_score))

            short_bal = getattr(row, "short_sale_balance", None)
            meta: dict = {
                "close":                   round(row.close, 2),
                "price_change_pct":        round(row.price_change * 100, 4),
                "margin_change_pct":       round(row.margin_change * 100, 4),
                "margin_purchase_balance": int(row.margin_purchase_balance),
                "margin_signal":           margin_score,
                "divergence_signal":       diverge_score,
                "margin_weight":           self.margin_weight,
                "divergence_weight":       self.divergence_weight,
                "window":                  self.window,
            }
            if short_bal is not None:
                meta["short_sale_balance"] = int(short_bal)

            signals.append(make_signal(
                stock_id=row.stock_id,
                date=row.date,
                signal_name=self.name,
                signal_value=round(row.margin_purchase_balance, 0),
                score=final_score,
                metadata=meta,
            ))

        return signals

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _margin_signal(self, margin_change: float) -> float:
        if margin_change > self.surge_threshold:
            return -1.0
        if margin_change < -self.unwind_threshold:
            return +1.0
        return 0.0

    def _divergence_signal(self, price_change: float, margin_change: float) -> float:
        price_up   = price_change  > 0
        price_down = price_change  < 0
        margin_up  = margin_change > 0
        margin_dn  = margin_change < 0

        if price_up   and margin_dn:  return +1.0
        if price_down and margin_up:  return -1.0
        if price_up   and margin_up:  return -0.4
        if price_down and margin_dn:  return +0.4
        return 0.0
