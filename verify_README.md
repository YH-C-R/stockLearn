# Phase 1 — Verification Guide

All commands are run from the **project root**.

---

## Demo

### `main.py` — Full pipeline demo

Fetches 2330 daily price data, validates it, caches it, prints a summary, and saves charts to `outputs/`.

```bash
python3 main.py
```

**Output:**
- Console summary (rows, date range, OHLC stats, first 5 rows)
- `outputs/2330_phase1.png` — closing price + MA5/MA20, volume, daily return

---

### `scripts/smoke_test_phase1.py` — Quick smoke test

Same pipeline as `main.py` but lighter — no MA overlay, cleans up the cache entry on exit.

```bash
python3 scripts/smoke_test_phase1.py
```

**Output:**
- Console step-by-step log
- `scripts/smoke_test_2330.png` — closing price + volume chart

---

## Unit Tests

Run all unit tests:

```bash
python3 -m pytest tests/unit/ -v
```

| File | What it tests |
|---|---|
| `tests/unit/test_schema.py` | `DailyPrice` Pydantic model |
| `tests/unit/test_cache.py` | Parquet save / load / invalidate |
| `tests/unit/test_price_fetcher.py` | FinMind fetcher (mocked HTTP) |
| `tests/unit/test_price_volume.py` | Price-volume strategy logic |

### `test_schema.py`

```bash
python3 -m pytest tests/unit/test_schema.py -v
```

| Test | Description |
|---|---|
| `test_valid_record_passes` | Happy path round-trip |
| `test_record_is_immutable` | `frozen=True` enforced |
| `test_empty_stock_id_fails` | Whitespace-only ID rejected |
| `test_zero_price_fails[open/high/low/close]` | Zero price rejected |
| `test_negative_price_fails[open/high/low/close]` | Negative price rejected |
| `test_negative_volume_fails` | Negative volume rejected |
| `test_zero_volume_passes` | Zero volume allowed (trading halt) |
| `test_high_less_than_low_fails` | OHLC consistency check |
| `test_open_above_high_fails` | OHLC consistency check |
| `test_close_below_low_fails` | OHLC consistency check |

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

### `test_price_volume.py`

```bash
python3 -m pytest tests/unit/test_price_volume.py -v
```

| Test | Description |
|---|---|
| `test_breakout_with_volume_surge_generates_signal` | Breakout + volume surge → score 0.8 |
| `test_breakout_with_strong_surge_scores_1` | Volume ≥ 2× threshold → score 1.0 |
| `test_breakout_without_volume_scores_0_4` | Breakout, no volume confirmation → score 0.4 |
| `test_no_breakout_produces_no_signal` | Flat price → no signal emitted |
| `test_close_below_rolling_high_produces_no_signal` | Close < rolling high → no signal |
| `test_signal_has_expected_fields` | stock_id, date, signal_name, score, direction all correct |
| `test_signal_metadata_contains_expected_keys` | All metadata keys present |
| `test_insufficient_history_produces_no_signal` | Too few rows for window → no signal |
| `test_min_close_filter_skips_cheap_stocks` | Rows below `min_close` ignored |
| `test_missing_required_column_raises` | `ValueError` on missing column |
| `test_multi_stock_signals_are_attributed_correctly` | Signal attributed to correct stock_id |

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

---

## Phase 2 Demo

### `scripts/demo_price_volume.py` — Price-volume strategy demo

Fetches 2330 daily price data, runs the price-volume breakout strategy, prints a signal summary, and saves a chart to `outputs/`.

```bash
python3 scripts/demo_price_volume.py
```

**Output:**
- Console: total signal count, breakdown by score tier, latest 10 signals with date / score / close / volume ratio
- `outputs/2330_price_volume.png` — closing price with signal markers (★ strong, ▲ surge, ● unconfirmed) + volume bars (red on signal days)

---

## Run Everything

```bash
# Unit tests only (no network)
python3 -m pytest tests/unit/ -v

# Integration tests (requires network)
python3 -m pytest tests/integration/ -v

# All tests
python3 -m pytest tests/ -v

# Phase 1 full demo
python3 main.py

# Phase 2 strategy demo
python3 scripts/demo_price_volume.py
```
