from __future__ import annotations

from datetime import date

from analysis.decision_engine import make_decision
from analysis.long_term_scorer import score_long_term
from analysis.short_term_scorer import score_short_term
from data.single_stock_loader import StockData, get_data_until


def get_daily_decision(data: StockData, current_date: date) -> dict:
    sliced = get_data_until(data, current_date)

    lt = score_long_term(sliced)
    st = score_short_term(sliced)
    dec = make_decision(lt, st)

    return {
        "date": current_date,
        "decision": dec.final_decision,
        "long_term_score": lt.long_term_score,
        "short_term_score": st.short_term_score,
        "volume_score": st.volume_score,
        "ma20": st.ma20,
        "ma60": st.ma60,
    }