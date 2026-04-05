# Stock Investment Strategy System
### Architecture & Implementation Guide
> **Strategies:** Davis Double · Margin Financing · Price & Volume Analysis

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Folder Structure](#2-folder-structure)
3. [Module Responsibilities](#3-module-responsibilities)
4. [Data Requirements](#4-data-requirements)
5. [API & Data Sources](#5-api--data-sources)
6. [Development Roadmap](#6-development-roadmap)
7. [Key Architectural Decisions](#7-key-architectural-decisions)

---

## 1. Project Overview

This system provides a modular, extensible framework for equity investment strategy research, signal generation, and backtesting. It is built around three core analytical pillars:

| Pillar | Description |
|---|---|
| **Davis Double Play** | Identify stocks with simultaneous EPS growth and P/E multiple expansion |
| **Margin Financing Trend** | Track changes in margin balances to gauge retail sentiment and smart-money divergence |
| **Price & Volume Analysis** | Detect accumulation, breakout, and distribution patterns using OHLCV data |

### Design Goals

> **Modular by design** — strategies, data layers, and backtesting are fully decoupled. Adding a new market or strategy requires no changes to core infrastructure.

Key design principles:

- Strategies **never fetch data directly** — they receive clean DataFrames from the processor layer
- Every strategy emits a **standardised `Signal` object** (`score`, `direction`, `confidence`, `timestamp`)
- **Point-in-time correctness** is enforced in backtesting to prevent look-ahead bias
- **Local caching** avoids repeated API calls during development and backtesting
- **Market calendar awareness** (TWSE trading days) is handled globally, not per-strategy

---

## 2. Folder Structure

```
stockAnalysis/
├── config/
│   ├── settings.py          # Markets, date ranges, signal thresholds
│   └── credentials.py       # API keys  (git-ignored)
│
├── data/
│   ├── fetchers/            # Raw acquisition (one class per data type)
│   │   ├── base.py
│   │   ├── price.py
│   │   ├── fundamentals.py
│   │   └── margin.py
│   ├── processors/          # Clean, normalise, derive fields
│   │   ├── base.py
│   │   ├── price.py
│   │   └── fundamentals.py
│   └── storage/             # Local cache + data contracts
│       ├── cache.py
│       └── schema.py
│
├── strategies/
│   ├── base.py              # Abstract Strategy interface
│   ├── davis_double.py
│   ├── margin_trend.py
│   ├── price_volume.py
│   └── combined.py          # Multi-signal aggregation
│
├── signals/
│   ├── base.py              # Signal dataclass
│   ├── aggregator.py        # Weighted combiner
│   └── filters.py           # Liquidity, sector, blacklist
│
├── backtesting/
│   ├── engine.py            # Event-driven backtest loop
│   ├── portfolio.py         # Position sizing, cash management
│   ├── metrics.py           # Sharpe, drawdown, win rate
│   └── report.py            # Charts and summary output
│
├── universe/
│   ├── screener.py          # Investable universe filter
│   └── index_members.py     # TWSE / OTC constituent loader
│
├── notebooks/               # Research and exploration
├── tests/
│   ├── unit/
│   └── integration/
├── outputs/                 # Reports, charts, backtest results
├── main.py                  # CLI entry point
└── requirements.txt
```

---

## 3. Module Responsibilities

### 3.1 `data/fetchers/`

Each fetcher inherits from `BaseFetcher`, which enforces a standard interface and handles rate-limiting and retry logic. Fetchers return **raw, unprocessed DataFrames** — they never apply business logic.

| File | Class | Responsibility |
|---|---|---|
| `base.py` | `BaseFetcher` | Abstract interface, retry logic, rate limiting |
| `price.py` | `PriceFetcher` | Daily OHLCV + turnover rate, adjusted prices |
| `fundamentals.py` | `FundamentalsFetcher` | Quarterly EPS, revenue, net income, PE ratio |
| `margin.py` | `MarginFetcher` | Daily margin balance, short balance, days-to-cover |

### 3.2 `data/processors/`

Processors receive raw DataFrames from fetchers and return clean, analysis-ready DataFrames. They handle missing values, alignment, split/dividend adjustment, and compute derived columns such as YoY EPS growth or relative volume.

### 3.3 `data/storage/`

- **`cache.py`** — transparent disk cache (Parquet format recommended). Never re-fetch within a backtest run. Include a `--refresh` flag for manual updates.
- **`schema.py`** — Pydantic/dataclass models that serve as contracts between layers. Any DataFrame entering a strategy must conform to the relevant schema.

### 3.4 `strategies/`

Each strategy answers a single question: *"Is this stock a buy signal based on criterion X?"* Strategies receive clean DataFrames and return `Signal` objects. They contain **no fetching or caching logic**.

| Module | Core Logic |
|---|---|
| `davis_double.py` | EPS growth YoY > threshold **AND** P/E ratio trending upward |
| `margin_trend.py` | Declining margin balance + rising price = smart-money signal |
| `price_volume.py` | MA breakouts, volume confirmation, accumulation detection |
| `combined.py` | Weighted aggregation of all strategy scores into one rank |

### 3.5 `signals/`

Normalises all strategy outputs into a unified dataclass. The aggregator applies configurable weights across strategies. Filters remove stocks that fail hard constraints (minimum liquidity, blacklist, sector exclusions).

```python
@dataclass
class Signal:
    ticker: str
    timestamp: datetime
    score: float        # 0.0 – 1.0
    direction: str      # "long" | "short" | "neutral"
    confidence: float   # 0.0 – 1.0
    source: str         # strategy name
```

### 3.6 `backtesting/`

An event-driven loop processes historical signals day by day, simulating portfolio construction and trade execution. Metrics are computed from the resulting equity curve. Reports are written to `outputs/`.

| File | Responsibility |
|---|---|
| `engine.py` | Daily-bar event loop, signal replay |
| `portfolio.py` | Position sizing, cash management, transaction costs |
| `metrics.py` | Sharpe ratio, max drawdown, win rate, CAGR |
| `report.py` | Equity curve charts, per-trade log, summary table |

### 3.7 `universe/`

Defines which stocks are eligible at any point in time.

- **`index_members.py`** — loads TWSE/OTC constituent lists with **historical membership** (critical for avoiding survivorship bias)
- **`screener.py`** — applies quantitative filters (minimum volume, price range, sector)

---

## 4. Data Requirements

### 4.1 Davis Double Play

| Field | Granularity | Notes |
|---|---|---|
| EPS (trailing & forward) | Quarterly | Requires ≥ 2 years of history for YoY growth |
| Revenue | Quarterly | Cross-check for EPS quality and sustainability |
| P/E Ratio (or Price + EPS) | Daily / Monthly | Detect P/E expansion trend over time |
| Net Income Margin | Quarterly | Trend direction confirms earnings quality |

**Derived signals:**
- EPS YoY growth rate > threshold (e.g. 15%)
- P/E trending **upward** while EPS also grows = Davis Double confirmed

### 4.2 Margin Financing Trend

| Field | Granularity | Notes |
|---|---|---|
| Margin Balance (融資餘額) | Daily | Published daily by TWSE |
| Short Balance (融券餘額) | Daily | Used to compute long/short ratio |
| Margin Change Rate | Daily | Derived: day-over-day % change in balance |
| Days to Cover | Daily | Short balance ÷ average daily volume |

**Derived signals:**
- Declining margin + rising price → strong hands absorbing supply (bullish)
- Rising margin + rising price → momentum, but monitor for overleveraging risk

### 4.3 Price & Volume Analysis

| Field | Granularity | Notes |
|---|---|---|
| OHLCV | Daily | Adjusted for splits and dividends |
| Turnover Rate (週轉率) | Daily | TWSE-specific; % of float traded |
| Relative Volume | Daily | Current volume vs. 20-day moving average |
| Moving Averages | Derived | 5 / 10 / 20 / 60-day MA from OHLCV |
| Volume-Price Divergence | Derived | Price up + volume down = weakening trend |

**Derived signals:**
- Price closing above MA on above-average volume = breakout confirmation
- Flat price + declining volume = supply absorption (accumulation pattern)

---

## 5. API & Data Sources

### 5.1 Taiwan (Primary Market)

| Source | Data Provided | Access |
|---|---|---|
| **FinMind** | OHLCV, EPS, margin balance, financials, index members | Free tier covers most needs. Best Python library. **Recommended starting point.** |
| **TWSE OpenAPI** | Daily prices, margin data, index constituents | Free REST API. Official source. Combine with FinMind for reliability. |
| **TEJ (tejapi)** | Full institutional-grade TW data | Paid subscription. Most complete. Use when free tiers are insufficient. |
| **goodinfo.tw** | Manual reference / validation only | Do not scrape programmatically. |

### 5.2 Global Markets (Future Extensibility)

| Source | Coverage | Notes |
|---|---|---|
| **yfinance** | US + global | Free. Good price/basic fundamentals. Best for rapid prototyping. |
| **Alpha Vantage** | US + global | Free tier. Provides EPS estimates and income statements. |
| **Financial Modeling Prep** | Global | Strong fundamentals API. Paid tiers. Good for multi-country expansion. |
| **Polygon.io** | US equities | Excellent price/volume quality. Paid. Ideal for US live trading. |

> **Recommendation:** Start with **FinMind** for Taiwan (free tier is sufficient for Phases 1–3). Add **yfinance** as a global fallback when expanding to other markets.

---

## 6. Development Roadmap

### Phase 1 — Foundation `Weeks 1–2`

- [ ] Define data contracts in `data/storage/schema.py` using Pydantic models
- [ ] Implement `data/fetchers/price.py` with FinMind integration
- [ ] Add local Parquet caching in `data/storage/cache.py` immediately
- [ ] Configure `config/settings.py`: markets, thresholds, market calendar (`exchange_calendars` library)

### Phase 2 — Strategy Modules `Weeks 3–4`

- [ ] Implement `data/fetchers/fundamentals.py` and `data/fetchers/margin.py`
- [ ] Build `strategies/price_volume.py` first — simplest, pure price data only
- [ ] Build `strategies/margin_trend.py` — add margin signal layer
- [ ] Build `strategies/davis_double.py` — most complex, requires clean quarterly EPS

### Phase 3 — Signal Layer `Week 5`

- [ ] Define `Signal` dataclass in `signals/base.py`
- [ ] Implement `signals/aggregator.py` with configurable strategy weights
- [ ] Build `strategies/combined.py` for multi-signal scoring
- [ ] Implement `universe/screener.py` with liquidity and sector filters

### Phase 4 — Backtesting Engine `Weeks 6–8`

- [ ] Build `backtesting/engine.py` as a daily-bar event-driven loop
- [ ] Implement `backtesting/portfolio.py`: position sizing, cash management, transaction costs
- [ ] Compute performance metrics in `backtesting/metrics.py`
- [ ] Generate output charts and summary tables in `backtesting/report.py`

### Phase 5 — Polish & Extensibility `Ongoing`

- [ ] Write unit tests (`tests/unit/`) for each strategy and processor
- [ ] Write integration tests (`tests/integration/`) with cached sample data
- [ ] Abstract fetcher layer for multi-country support (US, HK, JP)
- [ ] Add Jupyter notebooks in `notebooks/` for strategy research and validation

---

## 7. Key Architectural Decisions

Make these decisions early — changing them later is costly.

| Decision | Recommendation |
|---|---|
| **Data contracts** | Use Pydantic models in `schema.py` from day one. Sloppy shapes cause subtle backtesting bugs that are hard to trace. |
| **Adjusted vs. unadjusted prices** | Store both. Use adjusted for signal calculation; use unadjusted for margin data alignment. |
| **Point-in-time correctness** | Financial data (EPS) must reflect what was known at the time, not restated values. FinMind handles this reasonably well. |
| **Signal interface contract** | All strategies return the same `Signal` object. This makes the aggregator trivial to extend with new strategies. |
| **Market calendar** | Use `exchange_calendars` or `pandas_market_calendars` for correct TWSE trading day alignment in backtesting. |
| **Caching strategy** | Cache to Parquet on first fetch. Never re-fetch within a backtest run. Include a `--refresh` flag for manual updates. |

---

*End of Document*
