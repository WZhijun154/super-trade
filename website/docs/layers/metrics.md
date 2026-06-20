---
title: Metrics
---

# Metrics — `super_trade.metrics`

Technical indicators and summary statistics for OHLCV bars. Every metric is a
**pure function returning a Polars expression**, so they compose directly into
`df.with_columns(...)` and work on multi-symbol panels via `.over("symbol")`.

```python
from super_trade import metrics as m

df = store.read_bars("600519", Interval.DAY).with_columns(
    m.sma("close", 20).alias("sma_20"),
    m.rsi("close", 14).alias("rsi_14"),
)
df = df.with_columns(m.macd().alias("macd")).unnest("macd")   # struct output
```

## Two kinds

- **Per-bar indicators** — one value *per bar* (a column): `sma`, `ema`, `wma`,
  `rsi`, `roc`, `momentum`, `stochastic_oscillator`, `williams_r`, `cci`,
  `true_range`, `atr`, `bollinger_bands`, `rolling_volatility`, `obv`, `vwap`,
  `volume_sma`, `simple_return`, `log_return`, `cumulative_return`, `drawdown`.
- **Scalar summary stats** — one value for the *whole series* (use in `select` /
  `group_by().agg()`): `total_return`, `cagr`, `annualized_volatility`,
  `sharpe_ratio`, `sortino_ratio`, `max_drawdown`, `calmar_ratio`.

`METRICS` is a name→function registry. `STRUCT_METRICS` flags multi-output metrics
(returning a struct to `.unnest()`); `SCALAR_METRICS` flags the aggregates.

## Per-symbol summary across a panel

```python
panel.group_by("symbol").agg(
    m.sharpe_ratio().alias("sharpe"),
    m.max_drawdown().alias("max_dd"),
)
```

Conventions: returns are simple/arithmetic, `periods_per_year=252` annualization.
RSI/ATR use Wilder's smoothing; EMA uses `adjust=False`.
