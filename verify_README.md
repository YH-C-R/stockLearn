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

---

## Integration Test

> Requires a live FinMind API connection. Rate-limited without a token.

```bash
python3 -m pytest tests/integration/ -v
```

| File | What it tests |
|---|---|
| `tests/integration/test_phase1_pipeline.py` | End-to-end: fetch → validate → cache → load |

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

## Run Everything

```bash
# Unit tests only (no network)
python3 -m pytest tests/unit/ -v

# Integration tests (requires network)
python3 -m pytest tests/integration/ -v

# All tests
python3 -m pytest tests/ -v

# Full demo
python3 main.py
```
