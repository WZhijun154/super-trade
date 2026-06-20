---
title: Visualization (viz)
---

# Visualization — `super_trade.viz`

Pure Plotly chart builders. Each is a `DataFrame -> go.Figure` function that
consumes bars (plus any metric columns the caller added) and never queries the
store or computes metrics itself.

```python
from super_trade import viz
from super_trade import metrics as m

df = store.read_bars("600519", Interval.DAY).with_columns(m.sma("close", 20).alias("sma_20"))
viz.candlestick(df, overlays=["sma_20"], title="600519").show()
```

## Builders

- `candlestick(df, overlays=...)` — single-panel candlestick with line overlays.
- `price_with_indicators(df, overlays=..., volume=True, subplots=[...])` —
  multi-panel: price + overlays on top, then volume and/or one panel per indicator
  group (e.g. RSI, MACD).
- `line_chart(df, columns)` — arbitrary line series.
- `equity_curve(df, column="equity")` / `drawdown_chart(df, column=...)` — used by
  backtest results.

Because metrics emit **named columns**, overlays/subplots compose generically — add
a new indicator and it is instantly chartable, with no change to the viz layer.

## Dashboard

`dashboard/app.py` is a thin Streamlit shell over `DataStore` + `metrics` + `viz`:
pick a symbol, toggle indicators, view the candlestick and a summary-stats table.

```bash
uv run streamlit run dashboard/app.py
```
