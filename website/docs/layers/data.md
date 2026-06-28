---
title: Storage (data)
---

# Storage — `super_trade.data`

Where bars live. The rest of the system depends on the `DataStore` interface, not
on ClickHouse.

## Model

`Bar` (Pydantic, frozen) — validated OHLCV with `symbol`, `interval`, `timestamp`
(UTC), `open/high/low/close`, `volume`. Validation enforces OHLC consistency
(`high >= low`, open/close within range, non-negative volume). `Interval` is a
`StrEnum` (`1m`/`5m`/`15m`/`30m`/`1h`/`1d`) with `.minutes` and `.is_intraday`
helpers; `BAR_COLUMNS` is the canonical column order.

## `DataStore` (ABC)

```python
class DataStore(ABC):
    def init_schema(self) -> None: ...
    def write_bars(self, bars) -> int: ...                 # list[Bar] or Polars DF
    def read_bars(self, symbol, interval, start=None, end=None) -> pl.DataFrame: ...
    def latest_timestamp(self, symbol, interval) -> datetime | None: ...  # cache key
    def list_symbols(self, interval=None) -> list[str]: ...
```

## ClickHouse backend

`ClickHouseStore` uses the official `clickhouse-connect` driver:

- **Bulk, columnar inserts** — never row-by-row ORM writes.
- **`ReplacingMergeTree`** keyed `(symbol, interval, timestamp)`, versioned by
  `ingested_at` — re-ingesting an overlapping range replaces rather than
  duplicates. Reads use `FINAL` to dedup at query time.
- **Column codecs** (`DoubleDelta` for timestamps, `Gorilla` for prices, `T64` for
  volume) — large compression wins on financial series.
- **`PARTITION BY toYYYYMM(timestamp)`** for time-range pruning.

`ClickHouseConfig` is a `pydantic-settings` model reading `CLICKHOUSE_*` from the
environment / `.env`.

## Intervals & resampling

**Store 1-minute bars as the single source of truth; derive coarser bars by
resampling on read.** One source of truth means no redundancy and guaranteed
consistency — a 5-minute bar is *always* exactly its five 1-minute bars, never a
separately-fetched series that can drift.

```python
from super_trade.data import Interval, load_bars

# Stored at 1m; resampled to 5m on the way out.
df = load_bars(store, "600519", Interval.FIVE_MINUTE, resample_from=Interval.MINUTE)

# Daily reads stay direct (no resample needed).
df = load_bars(store, "600519", Interval.DAY)
```

`load_bars(store, symbol, interval, start, end, *, resample_from=None)` reads
directly when `resample_from` is `None`, otherwise reads the finer series and calls
`resample(...)`. The transform itself is pure Polars (`data/resample.py`):
`resample(bars, target, *, source=Interval.MINUTE)`.

### Session-aware bucketing (the A-share catch)

A-share trading is **09:30–11:30 and 13:00–15:00 Beijing**, with a lunch break.
Naive wall-clock windows break: a 60-minute bar can't sit on an hour grid (09:30
isn't on the hour), and the morning and afternoon sessions can't share one offset.
So the resampler buckets **within each `(symbol, date, session)`**:

```
bucket = (minutes_since_session_open) // target.minutes
```

This is correct for every interval and **never crosses lunch or the overnight gap**.
OHLCV aggregates as `open=first`, `high=max`, `low=min`, `close=last`, `volume=sum`
(first/last ordered by timestamp). Intraday bars are labelled by the first 1-minute
instant in the bucket (UTC); daily bars by the Beijing date at UTC midnight (matching
the akshare daily convention). Resampling *up* to a finer interval raises
`ValueError`.

Real 1-minute history comes from **QMT** (`QmtSource`); akshare stays daily.
Everything downstream — metrics, both backtest tiers, execution — already takes a
bars DataFrame, so it consumes resampled frames unchanged. The examples and the
dashboard take an interval argument and resample from 1-minute when it's intraday.
