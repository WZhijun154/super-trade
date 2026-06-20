---
title: 指标（metrics）
---

# 指标 — `super_trade.metrics`

面向 OHLCV 的技术指标与汇总统计。每个指标都是**返回 Polars 表达式的纯函数**，因此可直接
组合进 `df.with_columns(...)`，并可通过 `.over("symbol")` 作用于多 symbol 面板。

```python
from super_trade import metrics as m

df = store.read_bars("600519", Interval.DAY).with_columns(
    m.sma("close", 20).alias("sma_20"),
    m.rsi("close", 14).alias("rsi_14"),
)
df = df.with_columns(m.macd().alias("macd")).unnest("macd")   # struct 输出
```

## 两类指标

- **逐 bar 指标**——每个 bar 一个值（一列）：`sma`、`ema`、`wma`、`rsi`、`roc`、
  `momentum`、`stochastic_oscillator`、`williams_r`、`cci`、`true_range`、`atr`、
  `bollinger_bands`、`rolling_volatility`、`obv`、`vwap`、`volume_sma`、
  `simple_return`、`log_return`、`cumulative_return`、`drawdown`。
- **标量汇总统计**——对*整段序列*得到一个值（用于 `select` / `group_by().agg()`）：
  `total_return`、`cagr`、`annualized_volatility`、`sharpe_ratio`、`sortino_ratio`、
  `max_drawdown`、`calmar_ratio`。

`METRICS` 是“名称→函数”的注册表。`STRUCT_METRICS` 标记多输出指标（返回需 `.unnest()` 的
struct）；`SCALAR_METRICS` 标记标量聚合。

## 面板上的按 symbol 汇总

```python
panel.group_by("symbol").agg(
    m.sharpe_ratio().alias("sharpe"),
    m.max_drawdown().alias("max_dd"),
)
```

约定：收益率为简单（算术）收益，年化因子 `periods_per_year=252`。RSI/ATR 使用 Wilder
平滑；EMA 使用 `adjust=False`。
