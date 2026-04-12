# Stock Analysis Tool

A Taiwan stock analysis and backtesting tool built in Python.
Pulls market data from the **FinMind API** and runs a two-layer scoring system to produce actionable trading decisions.

---

## Table of Contents

1. [How It Works](#1-how-it-works)
2. [Quick Start](#2-quick-start)
3. [Project Structure](#3-project-structure)
4. [Data Layer](#4-data-layer)
5. [Scoring Layer](#5-scoring-layer)
6. [Decision Layer](#6-decision-layer)
7. [Strategy Layer](#7-strategy-layer)
8. [Backtest Layer](#8-backtest-layer)
9. [Pipeline Diagrams](#9-pipeline-diagrams)

---

## 1. How It Works

The tool uses a **two-layer decision framework**:

| Layer | Question | Output |
|---|---|---|
| Long-term scorer | Is this company fundamentally strong? | Score 0–1, class: `STRONG_LONG / NEUTRAL / WEAK` |
| Short-term scorer | Is now a good time to enter? | Score 0–1, signal: `GOOD_ENTRY / WAIT / AVOID` |
| Decision engine | Combine both layers | `STRONG_BUY / BUY / TRADE / WAIT / AVOID` |
| Recommendation | User-facing output | Plain-language summary + action |

---

## 2. Quick Start

### Prerequisites

```bash
pip install -r requirements.txt
```

Set your FinMind API token in `config/credentials.py`:
```python
FINMIND_TOKEN = "your_token_here"   # or None for anonymous (rate-limited)
```

### Run a full analysis

```bash
python3 scripts/analyze_stock.py 2330 2023-01-01 2026-04-10
```

Output sections:
1. Data summary (rows, coverage)
2. Strategy signals (price/volume, margin, Davis Double)
3. Combined score
4. Recommendation
5. Long-term fundamental score
6. Short-term timing score
7. Final decision

### Run a backtest

```bash
python3 scripts/run_backtest.py 2330 2023-01-01 2026-04-10
```

Output: metrics (win rate, total return, max drawdown) + first 5 trades.

---

## 3. Project Structure

```
stockAnalysis/
├── scripts/
│   ├── analyze_stock.py          # Full analysis report (main entry point)
│   └── run_backtest.py           # Backtest + metrics (main entry point)
│
├── data/
│   ├── single_stock_loader.py    # load_stock(), get_data_until(), StockData
│   └── fetchers/
│       ├── price.py              # FinMind daily OHLCV
│       ├── margin.py             # FinMind margin balance
│       └── fundamentals.py       # FinMind quarterly EPS
│
├── analysis/
│   ├── long_term_scorer.py       # EPS / PE / growth → LongTermScoreResult
│   ├── short_term_scorer.py      # Price / volume / margin → ShortTermScoreResult
│   ├── decision_engine.py        # Combine LT + ST → FinalDecisionResult
│   ├── recommendation.py         # Decision → RecommendationResult
│   ├── daily_decision.py         # Single-day wrapper (used by backtest)
│   ├── backtest.py               # Backtest loop
│   ├── backtest_metrics.py       # Win rate, return, drawdown
│   ├── single_stock_analysis.py  # Run all 3 strategies on StockData
│   └── single_stock_scoring.py   # Aggregate strategy signals into score
│
├── strategies/
│   ├── price_volume.py           # PriceVolumeStrategy
│   ├── margin_trend.py           # MarginTrendStrategy
│   └── davis_double.py           # DavisDoubleStrategy
│
├── signals/
│   ├── base.py                   # Signal dataclass
│   └── aggregator.py             # Weighted signal combiner
│
└── config/
    ├── settings.py               # Global thresholds and windows
    └── credentials.py            # API token (git-ignored)
```

---

## 4. Data Layer

### `StockData`

The central object passed to every module. Created by `load_stock()`.

```python
from data.single_stock_loader import load_stock
from datetime import date

data = load_stock("2330", date(2023, 1, 1), date(2026, 4, 10), token=TOKEN)
```

| Attribute | Type | Description |
|---|---|---|
| `stock_id` | `str` | Taiwan stock ticker |
| `start_date` | `date` | Requested start |
| `end_date` | `date` | Requested end |
| `warnings` | `list[str]` | Non-fatal issues (missing data series, etc.) |
| `daily` | `DataFrame` | See columns below |

**`daily` DataFrame columns:**

| Column | Type | Notes |
|---|---|---|
| `date` | `date` | Trading day |
| `close` | `float` | Closing price |
| `volume` | `float` | Daily volume |
| `margin_purchase_balance` | `float\|NaN` | Daily margin balance; NaN if unavailable |
| `eps` | `float\|NaN` | Quarterly EPS, forward-filled to daily; NaN if unavailable |
| `pe` | `float\|NaN` | `close / eps`; NaN where eps ≤ 0 |

### `get_data_until(data, current_date) -> StockData`

Returns a **new** `StockData` with only rows where `date <= current_date`.
Used internally by the backtest to prevent future data leakage.

```python
from data.single_stock_loader import get_data_until

sliced = get_data_until(data, date(2024, 6, 30))
```

---

## 5. Scoring Layer

### Long-Term Scorer

**File:** `analysis/long_term_scorer.py`
**Function:** `score_long_term(data) -> LongTermScoreResult`

Evaluates fundamental quality using three weighted components:

| Component | Weight | Logic |
|---|---|---|
| **EPS Trend** | 50% | YoY EPS growth consistency over last 8 quarters. Measures win-rate (% of positive YoY changes) and average growth magnitude. Falls back to linear slope when fewer than 5 quarters are available. |
| **PE Re-rating** | 30% | `current_pe / avg_pe`. Above historical average = market paying a premium = bullish. Penalises extreme overvaluation (ratio > 1.5). Returns neutral (0.5) when PE data unavailable. |
| **Revenue Growth** | 20% | YoY revenue % passed by caller. `≥20%` → 1.0, `≥10%` → 0.75, `0–10%` → 0.5, `<0%` → 0–0.25. Defaults to 0.5 (neutral) if not provided. |

**Classification thresholds:**

| Class | Score |
|---|---|
| `STRONG_LONG` | ≥ 0.7 |
| `NEUTRAL` | 0.4 – 0.7 |
| `WEAK` | < 0.4 |

**`LongTermScoreResult` fields:**

| Field | Type | Description |
|---|---|---|
| `stock_id` | `str` | |
| `long_term_score` | `float` | Weighted composite [0–1] |
| `classification` | `LongTermClass` | `STRONG_LONG / NEUTRAL / WEAK` |
| `eps_score` | `float` | EPS component score |
| `pe_score` | `float` | PE component score |
| `growth_score` | `float` | Revenue growth component score |
| `eps_quarters` | `list[float]` | Last 8 quarterly EPS values (oldest → latest) |
| `current_pe` | `float\|None` | Latest PE ratio |
| `avg_pe` | `float\|None` | Historical average PE |
| `revenue_growth` | `float\|None` | YoY revenue % passed by caller |
| `key_reasons` | `list[str]` | Up to 3 plain-language driver sentences |

---

### Short-Term Scorer

**File:** `analysis/short_term_scorer.py`
**Function:** `score_short_term(data) -> ShortTermScoreResult`

Evaluates timing and entry quality using three weighted components:

| Component | Weight | Logic |
|---|---|---|
| **Price Score** | 30% | Breakout above 20-day high → 1.0. Otherwise maps `close / MA20` linearly: `0.9×` → 0.0, `1.0×` → 0.5, `1.1×` → 1.0. |
| **Volume Score** | 40% | `current_volume / avg_volume(20d)`. `≥ 1.5×` → 1.0 (spike), `≥ 1.0×` → 0.75 (above avg), `< 1.0×` → 0.25 (weak). |
| **Margin Score** | 30% | 5-day vs prior 5-day average of `margin_purchase_balance`. Decreasing margin (unwinding retail leverage) is bullish. |

**Timing signal thresholds:**

| Signal | Score |
|---|---|
| `GOOD_ENTRY` | ≥ 0.7 |
| `WAIT` | 0.4 – 0.7 |
| `AVOID` | < 0.4 |

**`ShortTermScoreResult` fields:**

| Field | Type | Description |
|---|---|---|
| `stock_id` | `str` | |
| `short_term_score` | `float` | Weighted composite [0–1] |
| `timing_signal` | `TimingSignal` | `GOOD_ENTRY / WAIT / AVOID` |
| `price_score` | `float` | |
| `volume_score` | `float` | |
| `margin_score` | `float` | |
| `ma20` | `float\|None` | 20-day moving average |
| `ma60` | `float\|None` | 60-day moving average |
| `key_reasons` | `list[str]` | Up to 3 plain-language driver sentences |

---

## 6. Decision Layer

### Decision Engine

**File:** `analysis/decision_engine.py`
**Function:** `make_decision(lt, st) -> FinalDecisionResult`

Combines long-term classification and short-term timing signal using a fixed matrix:

| Long-term Class | Timing Signal | Decision |
|---|---|---|
| `STRONG_LONG` | `GOOD_ENTRY` | `STRONG_BUY` |
| `STRONG_LONG` | `WAIT` | `WAIT` |
| `STRONG_LONG` | `AVOID` | `AVOID` |
| `NEUTRAL` | `GOOD_ENTRY` | `TRADE` |
| `NEUTRAL` | `WAIT` | `WAIT` |
| `NEUTRAL` | `AVOID` | `AVOID` |
| `WEAK` | any | `AVOID` |

**Confidence score** = `0.7 × long_term_score + 0.3 × short_term_score`

**`FinalDecisionResult` fields:**

| Field | Type | Description |
|---|---|---|
| `stock_id` | `str` | |
| `final_decision` | `FinalDecision` | `STRONG_BUY / BUY / TRADE / WAIT / AVOID` |
| `action` | `Action` | Simplified: `BUY / WAIT / AVOID` |
| `confidence_score` | `float` | Weighted composite |
| `long_term_class` | `LongTermClass` | From long-term scorer |
| `timing_signal` | `TimingSignal` | From short-term scorer |
| `long_term_score` | `float` | |
| `short_term_score` | `float` | |
| `reasons` | `list[str]` | Combined `[LT]` and `[ST]` prefixed reasons |

---

### Recommendation

**File:** `analysis/recommendation.py`
**Function:** `recommend_from_decision(decision) -> RecommendationResult`

Converts the internal decision into a user-facing output with a plain-language summary.

**`RecommendationResult` fields:**

| Field | Type | Description |
|---|---|---|
| `stock_id` | `str` | |
| `recommendation` | `Recommendation` | `STRONG BUY / BUY / WAIT / AVOID` |
| `action` | `str` | |
| `confidence` | `float` | |
| `summary` | `str` | One-sentence summary (Chinese) |
| `reasons` | `list[str]` | |

---

## 7. Strategy Layer

Used by `analyze_stock.py` to generate time-series signals. Not used in the backtest path.

### PriceVolumeStrategy

**File:** `strategies/price_volume.py`

Fires a signal on the **first day** of a new price breakout above the N-day rolling high, confirmed by volume.

**Entry conditions (all must be true):**
1. `close > rolling N-day high` (breakout)
2. `breakout_pct <= max_breakout_pct` (not overextended, default 8%)
3. Volume ≥ surge threshold — OR — `emit_weak_signals=True`

**Scores:**

| Condition | Score |
|---|---|
| Breakout + volume ≥ 2× threshold | 1.0 |
| Breakout + volume ≥ threshold | 0.8 |
| Breakout only, no volume (weak) | 0.4 |

Suppresses repeated signals until price pulls back below the rolling high and breaks out again.

**Key parameters:**

| Parameter | Default | Description |
|---|---|---|
| `price_window` | 20 | Rolling high lookback (days) |
| `volume_window` | 20 | Average volume lookback (days) |
| `volume_surge_mult` | 1.5 | Volume multiple required for confirmation |
| `max_breakout_pct` | 0.08 | Skip if price is >8% above rolling high |

---

### MarginTrendStrategy

**File:** `strategies/margin_trend.py`

Detects divergence between price direction and margin financing balance.

**Two sub-signals combined:**

**Sub-signal 1 — Margin trend:**
| Condition | Score |
|---|---|
| Margin balance up > surge threshold | -1.0 (retail crowding in, bearish) |
| Margin balance down > unwind threshold | +1.0 (leverage unwinding, bullish) |
| Otherwise | 0.0 (neutral) |

**Sub-signal 2 — Price vs margin divergence:**
| Condition | Score |
|---|---|
| Price up + margin down | +1.0 (healthy rally) |
| Price down + margin up | -1.0 (dangerous — price falling on rising leverage) |
| Price up + margin up | -0.4 (leveraged rally, weaker) |
| Price down + margin down | +0.4 (base-building) |

**Final score** = `margin_weight(0.5) × sub1 + divergence_weight(0.5) × sub2`
Only emits when `|score| >= min_abs_score`.

---

### DavisDoubleStrategy

**File:** `strategies/davis_double.py`

Classic Davis Double Play: EPS growth + PE expansion. At most **one signal per quarter**, triggered on the earnings release date.

**Entry conditions (all must be true):**
1. EPS YoY growth > 30% (configurable)
2. `close > MA` (price above moving average — PE expansion proxy)
3. `(close - MA) / MA <= 0.15` (not overextended, default 15%)

**Score** follows an exponential curve from 0.5 (at threshold) asymptotically approaching 1.0:

| EPS Growth | Score |
|---|---|
| 30% (threshold) | 0.50 |
| 40% | 0.64 |
| 50% | 0.74 |
| 100% | 0.93 |

**Key parameters:**

| Parameter | Default | Description |
|---|---|---|
| `ma_window` | 60 | MA lookback for PE expansion proxy |
| `yoy_threshold` | 0.30 | Minimum YoY EPS growth required |
| `max_ma_distance` | 0.15 | Max allowed distance above MA |

---

## 8. Backtest Layer

### Single-Day Decision

**File:** `analysis/daily_decision.py`
**Function:** `get_daily_decision(data, current_date) -> dict`

Slices data up to `current_date`, runs both scorers, returns:

```python
{
    "date":             date,
    "decision":         FinalDecision,
    "long_term_score":  float,
    "short_term_score": float,
    "volume_score":     float,
    "ma20":             float | None,
    "ma60":             float | None,
}
```

No future data is used — `get_data_until()` is called internally.

---

### Backtest Loop

**File:** `analysis/backtest.py`
**Function:** `run_backtest(data, holding_days=20) -> list[dict]`

Loops every trading day in chronological order. One position at a time, no overlapping trades.

**Entry rules (evaluated in order):**
1. `decision in {STRONG_BUY, BUY}` — primary signal
2. Fallback: `long_term_score ≥ 0.60` AND `short_term_score ≥ 0.65` AND `volume_score ≥ 0.75`
3. Trend filter (applied before both): **skip if `MA20 < MA60`** (not in uptrend)

**Exit rule:** sell exactly `holding_days` trading days after entry (default 20).

**Each completed trade:**

```python
{
    "entry_date":        date,
    "exit_date":         date,
    "entry_price":       float,
    "exit_price":        float,
    "return":            float,          # (exit - entry) / entry
    "decision":          str,            # decision that triggered entry
    "long_term_score":   float,
    "short_term_score":  float,
}
```

Trades with fewer than `holding_days` remaining are dropped (not left open).

---

### Backtest Metrics

**File:** `analysis/backtest_metrics.py`
**Function:** `summarize_backtest(trades) -> dict`

Incomplete trades (`return is None`) are ignored automatically.

```python
{
    "number_of_trades": int,
    "win_rate":         float,   # fraction of trades with return > 0
    "average_return":   float,   # mean per-trade return
    "total_return":     float,   # compounded ∏(1+r) - 1
    "max_drawdown":     float,   # worst peak-to-trough on equity curve
}
```

`max_drawdown` is computed on the compounded equity curve (not simple sum), so a 10% loss after a 5% gain produces the correct proportional drawdown.

---

## 9. Pipeline Diagrams

### `analyze_stock.py` pipeline

```
load_stock()
    │
    ├── analyze_stock()
    │     ├── PriceVolumeStrategy  → signals
    │     ├── MarginTrendStrategy  → signals
    │     └── DavisDoubleStrategy  → signals
    │
    ├── score_stock()              → combined score time-series
    │
    ├── score_long_term()          → LongTermScoreResult
    ├── score_short_term()         → ShortTermScoreResult
    ├── make_decision()            → FinalDecisionResult
    └── recommend_from_decision()  → RecommendationResult
```

### `run_backtest.py` pipeline

```
load_stock()
    │
    └── run_backtest()
          └── per trading day:
                get_data_until()         ← no future data
                    │
                    ├── score_long_term()
                    ├── score_short_term()
                    └── make_decision()
          │
          └── summarize_backtest()       → metrics dict
```

---

*Generated 2026-04-12*
