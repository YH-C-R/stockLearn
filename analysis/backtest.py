from __future__ import annotations

from analysis.daily_decision import get_daily_decision
from analysis.decision_engine import FinalDecision
from data.single_stock_loader import StockData

_ENTRY_SIGNALS = {FinalDecision.STRONG_BUY, FinalDecision.BUY}
_HOLD_DAYS = 20

# v2: fallback entry threshold
_LT_MIN = 0.60
_ST_MIN = 0.60


def _should_enter(result: dict) -> bool:
    decision = result["decision"]
    lt_score = result["long_term_score"]
    st_score = result["short_term_score"]
    volume_score = result.get("volume_score")
    ma20 = result.get("ma20")
    ma60 = result.get("ma60")

    # 趨勢過濾：不在上升趨勢就不買
    if ma20 is not None and ma60 is not None and ma20 < ma60:
        return False

    # 優先使用正式決策
    if decision in _ENTRY_SIGNALS:
        return True

    # fallback：雙分數夠 + 量能夠
    if (
        lt_score >= 0.60
        and st_score >= 0.65
        and volume_score is not None
        and volume_score >= 0.75
    ):
        return True

    return False


def run_backtest(data: StockData, holding_days: int = _HOLD_DAYS) -> list[dict]:
    """Loop through every trading day and simulate fixed-hold trades.

    Entry rule :
      - enter when decision is STRONG_BUY or BUY
      - OR fallback entry when long_term_score >= 0.60 and short_term_score >= 0.60
      - only one position at a time

    Exit rule  :
      - exit exactly holding_days trading days after entry

    Returns
    -------
    List of completed trades:
        [
            {
                "entry_date":  date,
                "exit_date":   date,
                "entry_price": float,
                "exit_price":  float,
                "return":      float,
                "decision":    str,
                "long_term_score": float,
                "short_term_score": float,
            },
            ...
        ]
    """
    daily = (
        data.daily[["date", "close"]]
        .dropna(subset=["close"])
        .sort_values("date")
        .reset_index(drop=True)
    )

    if daily.empty:
        return []

    dates = daily["date"].tolist()
    prices = dict(zip(daily["date"], daily["close"]))

    trades: list[dict] = []
    exit_idx: int | None = None

    for i, current_date in enumerate(dates):
        # exit
        if exit_idx is not None:
            if i >= exit_idx:
                exit_date = dates[i]
                exit_price = prices[exit_date]

                trades[-1]["exit_date"] = exit_date
                trades[-1]["exit_price"] = exit_price
                trades[-1]["return"] = round(
                    (exit_price - trades[-1]["entry_price"]) / trades[-1]["entry_price"],
                    6,
                )
                exit_idx = None
            else:
                continue

        # entry
        result = get_daily_decision(data, current_date)

        if _should_enter(result):
            scheduled = i + holding_days
            if scheduled >= len(dates):
                break

            entry_price = prices[current_date]
            trades.append(
                {
                    "entry_date": current_date,
                    "exit_date": None,
                    "entry_price": entry_price,
                    "exit_price": None,
                    "return": None,
                    "decision": result["decision"].value,
                    "long_term_score": round(result["long_term_score"], 4),
                    "short_term_score": round(result["short_term_score"], 4),
                }
            )
            exit_idx = scheduled

    return trades