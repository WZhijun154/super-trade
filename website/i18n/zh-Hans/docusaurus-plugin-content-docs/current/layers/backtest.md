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

## 局限性 — 当前**未**建模的部分

向量化引擎以**分数目标权重**运作，单策略、单标的。这让它快速且易组合，但也因此**无法**
表达以下真实世界的摩擦：

| 关注点 | 是否建模 | 原因 / 需要什么 |
|---|---|---|
| 手续费 / 印花税 / 滑点 | ✅ 由 `CostModel` 处理 | 按换手收取；印花税仅卖出方 |
| **资金约束**——现金余额、整数手、不能超出可用现金买入 | ❌ | 需要跟踪现金 + 股数的账户模型 |
| **被迫清仓**——保证金强平 | ❌ | 路径依赖；需要逐 bar 检查权益的顺序循环 |
| **多策略资金竞争** | ❌ | 需要在多策略间分配同一资金池的组合层 |

后三者都是**组合层面且路径依赖**的——对一个向量化权重引擎而言结构性地无法实现：它假设
你总能以无限可分的资金精确达到目标权重，并一次性计算整段序列。

:::caution 据此解读结果
请把向量化结果当作**信号研究**——“扣除成本后，这个超额收益是否存在？”——而不是用真金
白银执行该策略的忠实模拟。
:::

## 事件驱动回测

`execution.EventDrivenBacktest` 是第二档。它**逐 bar**地把历史回放到执行层的
`SimBroker` + `RiskManager`（与实盘相同的机制），因此能建模向量化引擎无法处理的**路径
依赖**行为：**止损**，以及真实现金、整数手、按标的的仓位上限（资金约束）。它位于
[`execution`](./execution)（依赖 broker），并复用 `BacktestResult` 输出统计与图表。

```python
from super_trade.execution import EventDrivenBacktest, RiskManager, RiskLimits

result = EventDrivenBacktest(
    store, SmaCross(10, 30), cash=1_000_000, universe=["600519"],
    risk=RiskManager(RiskLimits(stop_loss=0.08)),
).run()
print(result.stats())          # 与向量化运行相同的 BacktestResult API
result.equity_curve().show()
```

策略的目标列在窗口上一次性预计算——这是合法的（无未来函数），因为指标是因果的。这正是
**在实盘前验证止损**的那一档：在 sandbox 上，8% 止损把最大回撤从 −23.5% 降到 −4.8%
（相比向量化运行）。

仍仅向量化 / 未来：在**多个**策略间分配资金池（多策略资金竞争）、保证金/强平，以及通过
`.over("symbol")` 的截面权重。
