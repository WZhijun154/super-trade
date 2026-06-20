---
title: 可视化（viz）
---

# 可视化 — `super_trade.viz`

纯 Plotly 图表构建器。每个都是 `DataFrame -> go.Figure` 的函数，消费行情（外加调用方
添加的任意指标列），自身从不查询存储或计算指标。

```python
from super_trade import viz
from super_trade import metrics as m

df = store.read_bars("600519", Interval.DAY).with_columns(m.sma("close", 20).alias("sma_20"))
viz.candlestick(df, overlays=["sma_20"], title="600519").show()
```

## 构建器

- `candlestick(df, overlays=...)`——带折线叠加的单面板 K 线图。
- `price_with_indicators(df, overlays=..., volume=True, subplots=[...])`——多面板：
  顶部价格 + 叠加，随后是成交量和/或每组指标各一个面板（如 RSI、MACD）。
- `line_chart(df, columns)`——任意折线序列。
- `equity_curve(df, column="equity")` / `drawdown_chart(df, column=...)`——供回测结果
  使用。

由于指标产出的是**带名字的列**，叠加/子面板可以通用地组合——新增一个指标即可立刻绘制，
无需改动 viz 层。

## 仪表盘

`dashboard/app.py` 是 `DataStore` + `metrics` + `viz` 之上的薄 Streamlit 壳：选择
symbol、切换指标、查看 K 线图与汇总统计表。

```bash
uv run streamlit run dashboard/app.py
```
