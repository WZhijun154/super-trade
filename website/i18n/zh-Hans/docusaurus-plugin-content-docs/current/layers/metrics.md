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

- **逐 bar 指标**——每个 bar 一个值（一列）。
- **标量汇总统计**——对*整段序列*得到一个值（用于 `select` / `group_by().agg()`）。

:::tip[初次接触指标？]
先从 **SMA/EMA**（趋势）、**RSI** 与 **MACD**（动量）、**布林带** 与 **ATR**（波动率）、
以及 **夏普比率** + **最大回撤**（绩效）入手。其余都是这些思想的变体。
:::

## 指标参考

### 收益类（Returns）

价格变化了多少，是其它一切的基础。

| 函数 | 含义 / 如何解读 |
|---|---|
| `simple_return(col, periods)` | 相对 `periods` 根前的百分比变化：`pₜ/pₜ₋ₙ − 1`，即单期的普通收益率。 |
| `log_return(col, periods)` | 对数收益 `ln(pₜ/pₜ₋ₙ)`。可跨时间相加，因此更适合波动率与建模。 |
| `cumulative_return(col)` | 自第一根 bar 起的累计增长（起点为 `0`），即买入持有的净值形状。 |
| `drawdown(col)` | 距历史峰值的回撤——始终 ≤ 0。`−0.20` 表示比迄今最高价低 20%。 |

### 趋势类（Trend）

平滑噪声、揭示方向。

| 函数 | 含义 / 如何解读 |
|---|---|
| `sma(col, window)` | 简单移动平均——最近 `window` 根收盘的均值。价格在向上的 SMA 之上 = 上升趋势。 |
| `ema(col, span)` | 指数移动平均——更看重近期价格，因此比 SMA 对新行情反应更快。 |
| `wma(col, window)` | 线性加权移动平均——类似 SMA，但最近一根权重最大。 |
| `macd(col, fast, slow, signal)` | `EMA(fast) − EMA(slow)`（MACD 线）、其 EMA（信号线）及两者之差（柱）。MACD **上穿**信号线 = 多头动量，**下穿** = 空头。返回 struct → 需 `.unnest()`。 |

### 动量 / 振荡类（Momentum）

衡量速度以及是否超买/超卖。多为有界区间。

| 函数 | 含义 / 如何解读 |
|---|---|
| `rsi(col, window)` | 相对强弱指数，0–100，由平均涨幅与跌幅得出。常用阈值：**> 70 超买，< 30 超卖**。 |
| `roc(col, periods)` | `periods` 根内的百分比变化率——最原始的动量。 |
| `momentum(col, periods)` | 相对 `periods` 根前的绝对价格变化（`pₜ − pₜ₋ₙ`）。 |
| `stochastic_oscillator(window, smooth)` | 收盘价在近期高低区间中的位置：`%K`（原始）+ `%D`（平滑），0–100。接近 100 = 区间顶部。struct → `.unnest()`。 |
| `williams_r(window)` | 与随机指标同理，区间为 −100…0；收盘相对近期最高价的位置。 |
| `cci(window)` | 顺势指标——典型价格偏离其均值多少（以平均绝对偏差为单位）。±100 为常用带。 |

### 波动率类（Volatility）

价格波动有多大——用于风险、止损与突破。

| 函数 | 含义 / 如何解读 |
|---|---|
| `true_range(...)` | 包含跳空的真实波幅：`high−low` 与到前收盘的两个跳空之中的最大者。 |
| `atr(window)` | 平均真实波幅——平滑后的真实波幅。“每根 bar 大约波动多少？”常用于设定止损/仓位。 |
| `bollinger_bands(col, window, num_std)` | 一条移动平均（中轨）加上 ± `num_std` 个标准差的上下轨。波动大时带变宽；触及带提示价格被拉伸。struct → `.unnest()`。 |
| `rolling_volatility(col, window, periods)` | 收益率的滚动标准差——近期（未年化）波动率。 |

### 成交量类（Volume）

用成交活跃度确认价格走势。

| 函数 | 含义 / 如何解读 |
|---|---|
| `typical_price(...)` | `(high + low + close) / 3`——该 bar 的代表性价格。 |
| `obv(close, volume)` | 能量潮——上涨日**加上**成交量、下跌日**减去**成交量的累计值。OBV 上升可“确认”价格上升。 |
| `vwap(...)` | 成交量加权平均价——按成交量加权的均价，即大部分成交真正发生的价位。 |
| `volume_sma(window)` | 成交量的移动平均——用作基线以发现放量。 |

### 汇总统计（标量）

用一个数字概括整段序列——绩效与风险。

| 函数 | 含义 / 如何解读 |
|---|---|
| `total_return(col)` | 从首到尾的总收益率。 |
| `cagr(col, periods_per_year)` | 复合年化增长率——把总收益折算成平滑的年化速率。 |
| `annualized_volatility(col, periods_per_year)` | 收益率的年化标准差——核心“风险”数值。 |
| `sharpe_ratio(col, periods_per_year, risk_free_rate)` | **每单位总风险**所获收益（（均值 − 无风险）/ 波动率，年化）。粗略参考：≈1 尚可，> 2 优秀。 |
| `sortino_ratio(...)` | 类似夏普，但只惩罚**下行**波动——奖励波动主要朝上的策略。 |
| `max_drawdown(col)` | 整段序列中最严重的峰谷亏损（负数）。 |
| `calmar_ratio(col, periods_per_year)` | CAGR 除以最大回撤的幅度——每单位最坏亏损换来的收益。 |

## 注册表

`METRICS` 是“名称→函数”的注册表。`STRUCT_METRICS` 标记多输出指标（返回需 `.unnest()`
的 struct）；`SCALAR_METRICS` 标记标量聚合。

## 面板上的按 symbol 汇总

```python
panel.group_by("symbol").agg(
    m.sharpe_ratio().alias("sharpe"),
    m.max_drawdown().alias("max_dd"),
)
```

约定：收益率为简单（算术）收益，年化因子 `periods_per_year=252`。RSI/ATR 使用 Wilder
平滑；EMA 使用 `adjust=False`。
