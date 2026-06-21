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

- **Per-bar indicators** — one value *per bar* (a column).
- **Scalar summary stats** — one value for the *whole series* (use in `select` /
  `group_by().agg()`).

:::tip[New to indicators?]
Start with **SMA/EMA** (trend), **RSI** and **MACD** (momentum), **Bollinger Bands**
and **ATR** (volatility), and **Sharpe** + **max drawdown** (performance). The rest
are variations on these ideas.
:::

## Metric reference

### Returns

How much price changed. The building blocks for everything else.

| Function | What it measures / how to read it |
|---|---|
| `simple_return(col, periods)` | Percentage change vs `periods` bars ago: `pₜ/pₜ₋ₙ − 1`. The everyday return of one period. |
| `log_return(col, periods)` | Natural-log return `ln(pₜ/pₜ₋ₙ)`. Adds up across time, so it's preferred for volatility and modelling. |
| `cumulative_return(col)` | Total growth since the first bar (`0` at the start). The equity-curve shape of buy-and-hold. |
| `drawdown(col)` | How far below the running peak you are — always ≤ 0. `−0.20` = 20% below the best price so far. |

### Trend

Smooth out noise to reveal direction.

| Function | What it measures / how to read it |
|---|---|
| `sma(col, window)` | Simple moving average — the mean of the last `window` closes. Price above a rising SMA = uptrend. |
| `ema(col, span)` | Exponential MA — weights recent prices more, so it reacts faster than SMA to new moves. |
| `wma(col, window)` | Linearly-weighted MA — like SMA, but the most recent bar counts most. |
| `macd(col, fast, slow, signal)` | `EMA(fast) − EMA(slow)` (MACD line), its EMA (signal), and their gap (histogram). MACD crossing **above** its signal = bullish momentum; **below** = bearish. Returns a struct → `.unnest()`. |

### Momentum / oscillators

Gauge speed and whether a move is overstretched. Most are bounded ranges.

| Function | What it measures / how to read it |
|---|---|
| `rsi(col, window)` | Relative Strength Index, 0–100, from average gains vs losses. Common reads: **> 70 overbought, < 30 oversold**. |
| `roc(col, periods)` | Rate of change in percent over `periods` bars — raw momentum. |
| `momentum(col, periods)` | Absolute price change vs `periods` bars ago (`pₜ − pₜ₋ₙ`). |
| `stochastic_oscillator(window, smooth)` | Where the close sits in the recent high–low range: `%K` (raw) + `%D` (smoothed), 0–100. Near 100 = top of range. Struct → `.unnest()`. |
| `williams_r(window)` | Same idea as stochastic, scaled −100…0; close relative to the recent highest high. |
| `cci(window)` | Commodity Channel Index — how far the typical price is from its average, in mean-deviation units. ±100 are common bands. |

### Volatility

How much price moves — for risk, stops, and breakouts.

| Function | What it measures / how to read it |
|---|---|
| `true_range(...)` | The bar's true range **including overnight gaps**: max of `high−low` and the gaps to the previous close. |
| `atr(window)` | Average True Range — smoothed true range. "How much does it move per bar?" Widely used to size stops/positions. |
| `bollinger_bands(col, window, num_std)` | A moving average (middle) with bands at ± `num_std` standard deviations. Bands widen when volatile; touching a band hints at a stretched price. Struct → `.unnest()`. |
| `rolling_volatility(col, window, periods)` | Rolling standard deviation of returns — recent (un-annualized) volatility. |

### Volume

Confirm moves with trading activity.

| Function | What it measures / how to read it |
|---|---|
| `typical_price(...)` | `(high + low + close) / 3` — one representative price for the bar. |
| `obv(close, volume)` | On-Balance Volume — a running total that **adds** volume on up days and **subtracts** it on down days. Rising OBV confirms a rising price. |
| `vwap(...)` | Volume-Weighted Average Price — the average price weighted by volume, i.e. where most trading actually happened. |
| `volume_sma(window)` | Moving average of volume — a baseline to spot volume spikes. |

### Summary statistics (scalar)

One number for a whole series — performance and risk.

| Function | What it measures / how to read it |
|---|---|
| `total_return(col)` | Overall % gain from the first to the last bar. |
| `cagr(col, periods_per_year)` | Compound Annual Growth Rate — the total return expressed as a smooth yearly rate. |
| `annualized_volatility(col, periods_per_year)` | Annualized standard deviation of returns — the headline "risk" number. |
| `sharpe_ratio(col, periods_per_year, risk_free_rate)` | Return earned **per unit of total risk** ((mean − risk-free) / volatility, annualized). Rough guide: ~1 decent, > 2 strong. |
| `sortino_ratio(...)` | Like Sharpe, but only penalizes **downside** volatility — rewards strategies whose swings are mostly upward. |
| `max_drawdown(col)` | The worst peak-to-trough loss over the series (a negative number). |
| `calmar_ratio(col, periods_per_year)` | CAGR divided by the size of the max drawdown — return per unit of worst-case pain. |

## Registry

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
