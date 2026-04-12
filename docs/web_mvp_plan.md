# MVP Architecture Plan — FastAPI Web Interface

---

## 1. Recommended Project Structure

**Recommendation: single project, server-side rendering.**
No frontend/backend split. FastAPI + Jinja2 templates + HTMX for dynamic interactions. No build step, no npm, no React.

```
stockAnalysis/
├── web/
│   ├── app.py                  # FastAPI app entry point
│   ├── routes/
│   │   ├── stocks.py           # stock list: add / remove / list
│   │   └── analysis.py         # run analysis, backtest, chart data
│   ├── templates/
│   │   ├── base.html           # shared layout, nav, CSS links
│   │   ├── index.html          # main page: stock list + input
│   │   └── stock.html          # stock detail: charts, scores, recommendation
│   └── static/
│       └── style.css           # minimal custom styles
│
├── storage/
│   └── watchlist.json          # persisted stock list (simple flat file)
│
├── analysis/                   # existing — untouched
├── data/                       # existing — untouched
├── strategies/                 # existing — untouched
└── config/                     # existing — untouched
```

**Key choices:**
- **HTMX** — swap HTML fragments without a full page reload. No JS framework needed.
- **Chart.js** — render price + signal charts directly in the browser from JSON data.
- **`watchlist.json`** — plain JSON file for the stock list. SQLite is overkill for personal use.

---

## 2. Page Structure

### Page 1 — Index (`/`)

```
┌─────────────────────────────────────────────┐
│  Stock Analysis Tool                         │
├─────────────────────────────────────────────┤
│  [ Stock ID input ]  [ Add ]                 │
├─────────────────────────────────────────────┤
│  Watchlist                                   │
│  ┌──────────┬──────────────────┬──────────┐ │
│  │ 2330     │ TSMC             │ [ View ] │ │
│  │ 2308     │ Delta            │ [ View ] │ │
│  │ 2454     │ MediaTek         │ [ View ] │ │
│  └──────────┴──────────────────┴──────────┘ │
└─────────────────────────────────────────────┘
```

### Page 2 — Stock Detail (`/stock/{stock_id}`)

```
┌─────────────────────────────────────────────┐
│  ← Back   2330  TSMC                         │
├─────────────────────────────────────────────┤
│  RECOMMENDATION:  STRONG BUY                 │
│  Confidence: 0.82  |  Action: BUY            │
│  "基本面強勁 + 短期動能良好，可積極進場"           │
├─────────────────────────────────────────────┤
│  Price Chart (2 years)                       │
│  [close line + MA20 + MA60]                  │
│  ★ = Davis Double signal dates               │
│  ▲ = PriceVolume breakout signals            │
├─────────────────────────────────────────────┤
│  Long-Term Score     Short-Term Score        │
│  0.74  STRONG_LONG   0.71  GOOD_ENTRY        │
│  EPS:  0.81          Price:  0.75            │
│  PE:   0.62          Volume: 1.00            │
│  Growth: 0.50        Margin: 0.60            │
│  Last 4 EPS: 4.2→4.8→5.1→5.6               │
├─────────────────────────────────────────────┤
│  PE: 18.3  |  Avg PE: 15.1  |  EPS: 5.6     │
│  Margin balance: ↓ decreasing (bullish)      │
├─────────────────────────────────────────────┤
│  [ Run Backtest (2 years) ]                  │
│  ── appears after click ──                   │
│  Trades: 12  |  Win rate: 66%                │
│  Total return: +38%  |  Max drawdown: 8.7%   │
│  [ trade table: entry / exit / return ]      │
└─────────────────────────────────────────────┘
```

---

## 3. API / Route Design

| Method | Path | Returns | Description |
|---|---|---|---|
| `GET` | `/` | HTML | Index page with watchlist |
| `POST` | `/stocks/add` | HTML fragment | Add stock, re-render list (HTMX) |
| `DELETE` | `/stocks/{id}` | HTML fragment | Remove stock, re-render list (HTMX) |
| `GET` | `/stock/{id}` | HTML | Full stock detail page |
| `GET` | `/api/analysis/{id}` | JSON | Scores + decision + recommendation |
| `GET` | `/api/chart/{id}` | JSON | Price series + signal dates for Chart.js |
| `POST` | `/api/backtest/{id}` | JSON | Backtest results (triggered on demand) |

**Why separate `/api/analysis` and `/api/chart`:**
The analysis is fast; the chart data involves loading 2 years of daily rows. Splitting them lets the page render the scores first while the chart loads.

---

## 4. Data Flow

```
Browser                     FastAPI                      Existing Python
───────                     ───────                      ───────────────

GET /stock/2330
                    ──►  load from watchlist.json
                         render stock.html (skeleton)
                    ◄──  HTML page

(page loads, JS fires)

GET /api/analysis/2330
                    ──►  load_stock()
                         score_long_term()
                         score_short_term()
                         make_decision()
                         recommend_from_decision()
                         serialize to dict
                    ◄──  JSON

GET /api/chart/2330
                    ──►  load_stock()
                         analyze_stock()   (for signal dates)
                         serialize daily prices + signal dates
                    ◄──  JSON

(user clicks "Run Backtest")

POST /api/backtest/2330
                    ──►  load_stock()
                         run_backtest()
                         summarize_backtest()
                    ◄──  JSON
```

**`watchlist.json` format:**
```json
{
  "stocks": ["2330", "2308", "2454"]
}
```

---

## 5. Implementation Order

### Phase 1 — Working skeleton (build this first)
1. `web/app.py` — FastAPI app with static files + Jinja2
2. `storage/watchlist.json` + add/remove routes
3. Index page showing the list
4. Stock detail page that renders scores from `/api/analysis/{id}`
5. Basic recommendation display (no chart yet)

**Goal:** You can add stocks, click one, and see the recommendation and scores.

### Phase 2 — Chart
6. `/api/chart/{id}` endpoint serializing price series + Davis Double / PriceVolume signal dates
7. Chart.js integration in `stock.html` — price line, MA20, MA60, signal markers

### Phase 3 — Backtest on demand
8. `/api/backtest/{id}` endpoint
9. "Run Backtest" button in the page (HTMX `hx-post`, renders result inline)

### Phase 4 — Polish (later, only if needed)
- Loading spinners while analysis runs
- Date range selector
- Error messages when FinMind fetch fails
- Caching analysis results so repeated views don't re-fetch

---

## 6. Reuse vs New Code

### Reuse as-is (zero changes needed)

| Module | Used for |
|---|---|
| `data/single_stock_loader.py` | All data loading |
| `analysis/long_term_scorer.py` | Long-term score |
| `analysis/short_term_scorer.py` | Short-term score |
| `analysis/decision_engine.py` | Decision |
| `analysis/recommendation.py` | Recommendation |
| `analysis/single_stock_analysis.py` | Signal dates for chart markers |
| `analysis/backtest.py` | Backtest loop |
| `analysis/backtest_metrics.py` | Metrics |

### New code to write

| File | What it does |
|---|---|
| `web/app.py` | FastAPI setup, mounts routes |
| `web/routes/stocks.py` | Watchlist CRUD |
| `web/routes/analysis.py` | Calls existing Python, serializes to JSON |
| `web/templates/*.html` | UI |
| `web/static/style.css` | Minimal styles |

---

## Notes

- `run_backtest()` calls `get_daily_decision()` for every trading day (~480 calls for 2 years).
  For MVP this is fine since it's triggered on demand, not on page load.
  If it becomes too slow, add a simple `@lru_cache` or pre-compute on first request.
