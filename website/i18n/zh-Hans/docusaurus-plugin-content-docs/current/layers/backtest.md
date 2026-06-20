---
title: 回测（backtest）
---

# 回测 — `super_trade.backtest`

一个**向量化**引擎：策略以 Polars 表达式给出目标权重，盈亏在整个 DataFrame 上一次性
计算。它复用其下的每一层——信号来自 `metrics`、统计来自 `metrics.summary`、图表来自
`viz`、真实行情来自 `DataStore`。

```python
from super_trade.backtest import VectorizedEngine, SmaCross

bars = store.read_bars("600519", Interval.DAY)
result = VectorizedEngine().run(bars, SmaCross(10, 30))
print(result.stats())          # sharpe、cagr、max_drawdown、calmar 等
result.equity_curve().show()   # 经 viz 生成的 Plotly 图
```

## 策略

```python
class Strategy(ABC):
    name: str
    def positions(self) -> pl.Expr: ...   # 每个 bar 的目标权重
```

目标权重：`1.0` = 满仓多头，`0` = 空仓，负数 = 做空。示例：`BuyAndHold`、
`SmaCross(fast, slow)`、`RsiReversion(window, low, high)`——每个都基于 `metrics`。

## 难点的处理

- **杜绝未来函数**——引擎持有 `target.shift(1)`：在第 *t* 个 bar 的收盘做决策，在 *t+1*
  进场。由引擎强制，而非交给策略。
- **A 股交易成本**——`CostModel` 按换手收取佣金（双边）、**仅卖出收取印花税**（不对称）
  以及滑点。
- **`equity[0] == 1.0`**，使 `summary` 指标可直接在 equity 列上正确计算。

## 结果

`BacktestResult` 提供 `stats()`（汇总统计字典）、`trades()`（持仓变化）、以及
`equity_curve()` / `drawdown()`（Plotly 图）。

## 路线图

组合 / 截面回测（通过 `.over("symbol")` 给每只股票分配权重）、用于路径依赖撮合的事件
驱动引擎，以及仪表盘的回测页面。
