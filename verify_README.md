# Verification Guide — Phase 1, 2, 3 & 4

All commands are run from the **project root**.

---

## Run Everything (Quick Reference)

```bash
# All unit tests (no network required)
python3 -m pytest tests/unit/ -v

# All integration tests (requires FinMind API / network)
python3 -m pytest tests/integration/ -v

# All tests
python3 -m pytest tests/ -v

# Phase 1
python3 main.py
python3 scripts/smoke_test_phase1.py

# Phase 2 — price-volume
python3 scripts/demo_price_volume.py
python3 scripts/demo_pv_backtest.py

# Phase 2 — margin trend
python3 scripts/demo_margin_trend.py
python3 scripts/demo_margin_backtest.py

# Phase 2 — Davis Double
python3 scripts/demo_davis_double.py
python3 scripts/demo_davis_backtest.py

# Phase 3 — combined strategy
python3 scripts/demo_phase3_combined.py
python3 scripts/demo_phase3_backtest.py

# Phase 4 — single-stock full pipeline
python3 scripts/analyze_stock.py
python3 scripts/analyze_stock.py 2454
python3 scripts/analyze_stock.py 2454 2022-01-01 2022-12-31
```

---

## Demo Scripts

### Phase 1

#### `main.py` — Full pipeline demo
Fetches 2330 daily price data, validates it, caches it, prints a summary, and saves charts to `outputs/`.
```bash
python3 main.py
```
**Output:** Console summary + `outputs/2330_phase1.png`

---

#### `scripts/smoke_test_phase1.py` — Quick smoke test
Lighter version of `main.py` — no MA overlay, cleans up cache on exit.
```bash
python3 scripts/smoke_test_phase1.py
```
**Output:** Console step-by-step log + `scripts/smoke_test_2330.png`

---

### Phase 2 — Strategy Demos

#### `scripts/demo_price_volume.py`
Fetches 2330 price data, runs the price-volume breakout strategy, prints signal summary, saves chart.
```bash
python3 scripts/demo_price_volume.py
```
**Output:** Signal count by score tier + `outputs/2330_price_volume.png`

---

#### `scripts/demo_pv_backtest.py`
Generates price-volume signals and runs a fixed-holding-period backtest.
```bash
python3 scripts/demo_pv_backtest.py
```
**Output:** Trades, win rate, avg return, cumulative return, max drawdown, sample trades

---

#### `scripts/demo_margin_trend.py`
Fetches price and margin data, runs margin-trend strategy, prints signal summary, saves chart.
```bash
python3 scripts/demo_margin_trend.py
```
**Output:** Bullish/bearish signal breakdown + `outputs/2330_margin_trend.png`

---

#### `scripts/demo_margin_backtest.py`
Generates margin-trend signals and runs a fixed-holding-period backtest.
```bash
python3 scripts/demo_margin_backtest.py
```
**Output:** Trades, win rate, avg return, cumulative return, max drawdown, sample trades

---

#### `scripts/demo_davis_double.py`
Fetches price and EPS data, runs Davis Double strategy, prints alignment preview and signal summary, saves chart.
```bash
python3 scripts/demo_davis_double.py
```
**Output:** EPS alignment table, signal table + `outputs/2330_davis_double.png`

---

#### `scripts/demo_davis_backtest.py`
Generates Davis Double signals and runs a fixed-holding-period backtest.
```bash
python3 scripts/demo_davis_backtest.py
```
**Output:** Trades, win rate, avg return, cumulative return, max drawdown, sample trades

---

### Phase 3 — Combined Strategy

#### `scripts/demo_phase3_combined.py`
Runs the full combined strategy pipeline (screen → aggregate → rank) on a small universe, prints score breakdown and top-N selections.
```bash
python3 scripts/demo_phase3_combined.py
```
**Output:**
- Screening summary (stocks before/after)
- Signal counts per strategy
- Aggregated score sample (stock_id, pv_score, mt_score, dd_score, final_score)
- Top-N selected stocks for the latest signal dates

---

#### `scripts/demo_phase3_backtest.py`
Full Phase 3 backtest demo with default-parameter single run **and** a parameter sweep.
```bash
python3 scripts/demo_phase3_backtest.py
```
**Output:**
- Data fetch summary
- Screening result
- Combined strategy signal counts
- Single-run portfolio metrics (hold=20, top_n=3, min_score=0.3)
- Sample trades + per-stock summary
- Parameter sweep table (18 combinations of holding_days × top_n × min_score, sorted by cumulative return)
- Best and worst parameter combination

---

### Phase 4 — Single-Stock Full Pipeline

#### `scripts/analyze_stock.py`
Runs the complete single-stock analysis pipeline: load → strategies → score → recommendation.
```bash
# Default: TSMC 2023
python3 scripts/analyze_stock.py

# Custom ticker
python3 scripts/analyze_stock.py 2454

# Custom ticker + date range
python3 scripts/analyze_stock.py 2454 2022-01-01 2022-12-31
```
**Output:**
1. Data load summary (row count, date range, coverage per column)
2. Strategy signal counts (price_volume / margin_trend / davis_double)
3. Score snapshot (PV / MT / DD / final_score)
4. Recommendation report (price, MA20/MA50, PE, EPS trend, scores, recommendation, suggested entry)

---

## Unit Tests

```bash
python3 -m pytest tests/unit/ -v
```

| File | What it tests |
|---|---|
| `tests/unit/test_schema.py` | `DailyPrice` Pydantic model validators |
| `tests/unit/test_cache.py` | Parquet save / load / invalidate |
| `tests/unit/test_price_fetcher.py` | FinMind price fetcher (mocked HTTP) |
| `tests/unit/test_price_volume.py` | Price-volume strategy logic |
| `tests/unit/test_margin_trend.py` | Margin-trend strategy logic |
| `tests/unit/test_davis_double.py` | Davis Double strategy logic |
| `tests/unit/test_metrics.py` | Backtesting metric functions |

---

### `test_schema.py`
```bash
python3 -m pytest tests/unit/test_schema.py -v
```
| Test | Description |
|---|---|
| `test_valid_record_passes` | Happy path round-trip |
| `test_record_is_immutable` | `frozen=True` enforced |
| `test_empty_stock_id_fails` | Whitespace-only ID rejected |
| `test_zero_price_fails` | Zero price rejected (open/high/low/close) |
| `test_negative_price_fails` | Negative price rejected |
| `test_negative_volume_fails` | Negative volume rejected |
| `test_zero_volume_passes` | Zero volume allowed (trading halt) |
| `test_high_less_than_low_fails` | OHLC consistency check |
| `test_open_above_high_fails` | OHLC consistency check |
| `test_close_below_low_fails` | OHLC consistency check |

---

### `test_cache.py`
```bash
python3 -m pytest tests/unit/test_cache.py -v
```
| Test | Description |
|---|---|
| `test_save_creates_parquet_file` | File written with `.parquet` suffix |
| `test_load_returns_same_shape` | Row/column count survives round-trip |
| `test_load_returns_same_values` | Data integrity after serialisation |
| `test_load_returns_none_when_no_cache` | Cache miss returns `None` |
| `test_load_with_date_filter` | `start_date`/`end_date` filtering works |
| `test_invalidate_removes_file` | File deleted, returns `True` |
| `test_invalidate_returns_false_when_no_cache` | Missing file returns `False` |
| `test_unknown_dataset_raises` | `ValueError` on unknown dataset name |

---

### `test_price_fetcher.py`
```bash
python3 -m pytest tests/unit/test_price_fetcher.py -v
```
| Test | Description |
|---|---|
| `test_returned_dataframe_has_expected_columns` | Column rename contract |
| `test_returned_dataframe_is_not_empty` | Row count matches mocked payload |
| `test_rows_are_sorted_by_date` | Output sorted ascending by date |
| `test_empty_api_response_raises_value_error` | Empty `data` raises `ValueError` |
| `test_http_error_propagates` | HTTP 4xx/5xx surfaces as `HTTPError` |
| `test_invalid_rows_are_dropped` | Bad OHLC row dropped silently |

---

### `test_price_volume.py`
```bash
python3 -m pytest tests/unit/test_price_volume.py -v
```
| Test | Description |
|---|---|
| `test_breakout_with_volume_surge_generates_signal` | Breakout + surge → score 0.8 |
| `test_breakout_with_strong_surge_scores_1` | Volume ≥ 2× threshold → score 1.0 |
| `test_breakout_without_volume_scores_0_4` | No volume confirmation → score 0.4 |
| `test_no_breakout_produces_no_signal` | Flat price → no signal |
| `test_close_below_rolling_high_produces_no_signal` | Close < rolling high → no signal |
| `test_only_first_breakout_day_emits_signal` | Dedup: only day 1 of breakout fires |
| `test_new_breakout_fires_after_pullback` | Second breakout after pullback fires |
| `test_continuous_breakout_emits_only_one_signal` | Sustained breakout = one signal |
| `test_overextended_breakout_skipped` | `breakout_pct > max_breakout_pct` → skipped |
| `test_breakout_within_max_distance_passes` | Within threshold → signal emitted |
| `test_weak_signal_suppressed_when_flag_false` | `emit_weak_signals=False` suppresses 0.4 |
| `test_strong_signal_emitted_regardless_of_flag` | Strong signal always emitted |
| `test_signal_has_expected_fields` | All Signal fields correct |
| `test_signal_metadata_contains_expected_keys` | All metadata keys present |
| `test_breakout_pct_in_metadata` | `breakout_pct` value correct |
| `test_volume_excess_pct_in_metadata` | `volume_excess_pct` value correct |
| `test_insufficient_history_produces_no_signal` | Too few rows → no signal |
| `test_min_close_filter_skips_cheap_stocks` | Below `min_close` → ignored |
| `test_missing_required_column_raises` | `ValueError` on missing column |
| `test_multi_stock_signals_attributed_correctly` | Signal attributed to correct stock |

---

### `test_margin_trend.py`
```bash
python3 -m pytest tests/unit/test_margin_trend.py -v
```
| Test | Description |
|---|---|
| `test_missing_margin_balance_raises` | Missing required column raises `ValueError` |
| `test_short_sale_balance_optional` | Works without `short_sale_balance` |
| `test_short_sale_balance_included_in_metadata_when_present` | Optional column in metadata |
| `test_bullish_signal_price_up_margin_down` | Price up + margin down → bullish |
| `test_bearish_signal_price_down_margin_up` | Price down + margin up → bearish |
| `test_no_signal_when_both_flat` | No change → no signal |
| `test_min_abs_score_filters_weak_signals` | High threshold reduces signals |
| `test_custom_weights_change_score` | Unequal weights produce different scores |
| `test_zero_weight_sum_raises` | Weights summing to zero raises `ValueError` |
| `test_weights_in_metadata` | Weight values recorded in metadata |
| `test_all_scores_within_bounds` | All scores in [-1.0, 1.0] |
| `test_insufficient_history_produces_no_signal` | Too few rows → no signal |

---

### `test_davis_double.py`
```bash
python3 -m pytest tests/unit/test_davis_double.py -v
```
| Test | Description |
|---|---|
| `test_growth_score_at_threshold` | Score = 0.5 at exact threshold |
| `test_growth_score_above_threshold` | Score > 0.5 above threshold |
| `test_growth_score_below_threshold` | Score = 0.5 below threshold |
| `test_growth_score_high_growth` | Score approaches 1.0 for very high growth |
| `test_effective_date_uses_release_date` | Release date preferred when present |
| `test_effective_date_falls_back_to_period_plus_45_days` | Q1/Q3 → +45 days |
| `test_effective_date_falls_back_to_period_plus_90_days` | Q2/Q4 → +90 days |
| `test_no_signal_when_yoy_below_threshold` | Growth below threshold → no signal |
| `test_signal_when_yoy_above_threshold` | Growth above threshold → signal |
| `test_no_signal_when_price_below_ma` | Price below MA → no signal |
| `test_no_signal_when_too_far_above_ma` | Price > `max_ma_distance` above MA → skip |
| `test_one_signal_per_quarter` | Only one signal per quarter per stock |
| `test_metadata_contains_expected_keys` | All metadata keys present |
| `test_missing_fundamentals_raises` | Missing required column raises `ValueError` |
| `test_insufficient_history_no_signal` | Fewer than 5 quarters → no YoY → no signal |
| `test_multi_stock_signals_attributed_correctly` | Signals attributed to correct stock |

---

### `test_metrics.py`
```bash
python3 -m pytest tests/unit/test_metrics.py -v
```
| Test | Description |
|---|---|
| `test_win_rate_all_winners` | 100% win rate |
| `test_win_rate_all_losers` | 0% win rate |
| `test_win_rate_mixed` | 50% win rate |
| `test_win_rate_zero_return_not_counted_as_win` | Flat return is not a win |
| `test_win_rate_empty_raises` | Empty series raises `ValueError` |
| `test_cumulative_return_single_trade` | Single trade computes correctly |
| `test_cumulative_return_two_trades_compound` | Compounding over two trades |
| `test_cumulative_return_gain_then_loss` | +50% then -50% = -25% |
| `test_cumulative_return_all_flat` | All zeros → 0% cumulative |
| `test_cumulative_return_empty_raises` | Empty series raises `ValueError` |
| `test_max_drawdown_no_loss` | Monotone gains → 0% drawdown |
| `test_max_drawdown_single_loss` | First-trade loss captured correctly |
| `test_max_drawdown_peak_then_trough` | -10% from peak captured |
| `test_max_drawdown_recovers_after_loss` | Drawdown measured at trough, not end |
| `test_max_drawdown_empty_returns_zero` | Empty → 0.0, no exception |
| `test_equity_curve_starts_at_first_trade_factor` | First value = 1 + r₀/100 |
| `test_equity_curve_monotone_on_all_gains` | Strictly increasing on all-positive |
| `test_equity_curve_empty_returns_empty` | Empty → empty Series |
| `test_compute_trade_metrics_known_values` | All five metrics correct together |
| `test_compute_trade_metrics_empty_returns_zeros` | Empty → zero-value dict |
| `test_compute_trade_metrics_keys_complete` | All five keys present |

---

## Integration Tests

> Requires a live FinMind API connection. Rate-limited without a token.

```bash
python3 -m pytest tests/integration/ -v
```

| File | What it tests |
|---|---|
| `tests/integration/test_phase1_pipeline.py` | End-to-end: fetch → validate → cache → load |
| `tests/integration/test_price_volume_pipeline.py` | End-to-end: fetch → price-volume strategy → signal validation |

---

### `test_phase1_pipeline.py`
| Test | Description |
|---|---|
| `test_fetched_df_is_not_empty` | API returns rows |
| `test_fetched_df_has_expected_columns` | Column contract |
| `test_fetched_df_contains_correct_stock_id` | No cross-stock contamination |
| `test_fetched_df_dates_within_range` | Dates respect start/end bounds |
| `test_all_rows_pass_schema_validation` | All rows valid per `DailyPrice` |
| `test_cached_df_is_not_none` | Cache load succeeds |
| `test_cached_df_shape_matches_fetched` | Shape preserved through Parquet |
| `test_cached_df_columns_match` | Columns preserved through Parquet |
| `test_cached_close_prices_match_fetched` | Close values identical |
| `test_cached_volumes_match_fetched` | Volume values identical |

---

### `test_price_volume_pipeline.py`
| Test | Description |
|---|---|
| `test_pipeline_returns_a_list` | `generate()` returns a list |
| `test_pipeline_produces_signals` | At least one signal over a full year |
| `test_all_signals_are_signal_instances` | All items are `Signal` objects |
| `test_signal_stock_id_is_correct` | All signals attributed to `2330` |
| `test_signal_dates_within_range` | All dates within requested range |
| `test_signal_name_is_correct` | `signal_name == "price_volume"` |
| `test_signal_scores_are_valid` | Scores are one of `{0.4, 0.8, 1.0}` |
| `test_all_signals_are_bullish` | Direction is `BULLISH` for all signals |
| `test_signal_value_is_positive` | Raw close price value is positive |
| `test_signal_metadata_keys_present` | All required metadata keys present |
