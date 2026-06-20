---
title: Acquisition (sources)
---

# Acquisition — `super_trade.sources`

Where bars come from. Ingestion depends on the `DataSource` interface; akshare is
the first implementation, QMT the precise/recent one.

## `DataSource` (ABC)

```python
class DataSource(ABC):
    def list_symbols(self) -> list[SymbolInfo]: ...
    def fetch_bars(self, symbol, interval, start=None, end=None,
                   adjust=Adjust.HFQ) -> list[Bar]: ...
```

`Adjust` is a `StrEnum`: `NONE` / `QFQ` (forward) / `HFQ` (backward). **HFQ** is the
default — stable over time and correct for backtesting.

## AkshareSource

Wraps every network call with a `RateLimiter` + `tenacity` retries, normalizes
akshare's Chinese-named columns into validated `Bar`s, and handles A-share quirks
(volume in 手/lots → shares; trading-date → UTC). Malformed rows are skipped.

:::warning[eastmoney throttling]
akshare scrapes per-IP-throttled sites. Keep `RateLimiter(min_interval)` ≥ 1–2s.
The historical-kline endpoint is also blocked from non-mainland / datacenter IPs.
:::

## QmtSource

Broker-grade data via the MiniQMT terminal + `xtquant` (no scraping/WAF/IP issues).
Model is **download → query**: `download_history_data` populates a local cache,
then `get_market_data_ex(..., dividend_type=...)`. `xtquant` is imported lazily, so
the module loads anywhere; the fetch path is verified on a MiniQMT machine.

Symbols map between the bare 6-digit code used in storage and QMT's
`CODE.EXCHANGE` form (`600519` ↔ `600519.SH`).
