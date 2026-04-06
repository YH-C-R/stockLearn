from abc import ABC, abstractmethod

import pandas as pd

from signals.base import Signal


class BaseStrategy(ABC):
    """Abstract interface that every strategy must implement.

    A strategy consumes one or more DataFrames (price, fundamentals, margin)
    and produces a flat list of Signal objects — one per stock per date.

    Subclass contract
    -----------------
    - Override `name` with a unique, machine-readable identifier.
    - Implement `generate()` to produce signals from input data.
    - Do not mutate input DataFrames; work on copies if transformation is needed.
    - Raise `ValueError` for missing required columns rather than failing silently.

    Usage example
    -------------
        class MaCrossover(BaseStrategy):
            name = "ma_crossover"

            def generate(self, price_df: pd.DataFrame, **kwargs) -> list[Signal]:
                ...
    """

    #: Unique strategy identifier — used as Signal.signal_name
    name: str = ""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "name", ""):
            raise TypeError(f"{cls.__name__} must define a non-empty class attribute 'name'")

    @abstractmethod
    def generate(self, price_df: pd.DataFrame, **kwargs: pd.DataFrame) -> list[Signal]:
        """Run the strategy and return a list of Signals.

        Parameters
        ----------
        price_df:
            Daily OHLCV DataFrame as produced by ``fetch_daily_price()``.
            Expected columns: stock_id, date, open, high, low, close, volume.
        **kwargs:
            Optional supplementary DataFrames passed by keyword, e.g.
            ``fundamentals_df=...`` or ``margin_df=...``.

        Returns
        -------
        list[Signal]
            One Signal per (stock_id, date) combination where the strategy
            produces a meaningful output. Empty list if no signal fires.
        """

    def validate_columns(self, df: pd.DataFrame, required: list[str], label: str = "df") -> None:
        """Raise ValueError if any required column is missing from df."""
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"{self.name}: {label} is missing columns: {missing}")
