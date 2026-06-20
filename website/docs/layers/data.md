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
`StrEnum` (`1m`/`5m`/`15m`/`1h`/`1d`); `BAR_COLUMNS` is the canonical column order.

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
