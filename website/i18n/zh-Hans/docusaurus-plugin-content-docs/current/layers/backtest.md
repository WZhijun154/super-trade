---
title: 回测（backtest）
---

# 回测 — `super_trade.backtest`

`super-trade` 有**两个回测引擎**，它们接受*同一个* `Strategy`，但计算方式根本不同：
快速的**向量化**引擎（`VectorizedEngine`）用于信号研究，以及忠实的**事件驱动**引擎
（`EventDrivenBacktest`）用于对执行敏感的逻辑。两者都复用其下各层——信号来自 `metrics`、
统计来自 `metrics.summary`、图表来自 `viz`、真实行情来自 `DataStore`——并都返回
`BacktestResult`。

```python
from super_trade.backtest import VectorizedEngine, SmaCross

bars = store.read_bars("600519", Interval.DAY)
result = VectorizedEngine().run(bars, SmaCross(10, 30))
print(result.stats())          # sharpe、cagr、max_drawdown、calmar 等
result.equity_curve().show()   # 经 viz 生成的 Plotly 图
```

## 向量化 vs 事件驱动

这是最重要的概念。两个引擎回答的是不同的问题。

### 向量化——一次性计算整体

`VectorizedEngine` 把回测当作**电子表格**：用数组运算（Polars）构建一整列一整列，**不对
bar 做 Python 循环**。

1. 策略**一次性给出每根 bar 的目标权重**——`Strategy.positions()` 是一个 Polars 表达式；
2. 把该列**滞后**一根（`shift(1)`），以便在*下一*根 bar 才交易——这就是它避免未来函数的方式；
3. 用持有权重乘以每根 bar 的收益、减去成本，再做累计乘积 → 得到净值曲线。

因为全是列运算，即使跨越多年数据也只需微秒级。代价是：它假设你**总能精确达到目标权重**、
资金无限可分，且**不保存任何演进状态**。因此它无法建模任何依赖*路径*的东西——你真实的
现金、整数手，或基于真实入场价触发的**止损**。

→ 用于**快速信号研究**：“扣除成本后，这条规则是否有超额收益？”

### 事件驱动——逐步推进、对状态做出反应

`EventDrivenBacktest` 做的是真实交易所做的事：它**逐 bar 循环**，每一步由**券商 +
风控对当前状态做出反应**——你的现金、你的持仓、此刻的价格——并决定订单。每根 bar：

1. 按市值标记账户；
2. 用每个持仓的真实入场价检查**止损** → 触发则卖出；
3. 评估策略信号 → 用你**真实拥有的现金与手数**为买单定量；
4. 通过 `SimBroker` 撮合订单，更新现金与持仓。

因为它携带**演进状态**并做**顺序决策**，所以能建模向量化引擎做不到的东西：止损、真实
现金/整手限制、按标的定量。它更慢（Python 循环），但忠实——而且**同一套循环驱动实盘**
（把 `SimBroker` 换成 `QmtBroker` 即可）。

→ 用于在实盘前**验证对执行敏感的逻辑**（尤其是止损）。

### 并排对比

| | 向量化（`VectorizedEngine`） | 事件驱动（`EventDrivenBacktest`） |
|---|---|---|
| 计算方式 | 一次性整列（无循环） | 逐 bar 循环 |
| 状态 | 无（假设总能达到目标权重） | 演进账户：现金 + 股数持仓 |
| 速度 | 非常快 | 较慢 |
| 止损 / 现金 / 手数 | ❌ 无法建模 | ✅ 建模 |
| 与实盘同一代码路径？ | 否 | 是（共用 broker + 风控循环） |
| 适用于 | 快速信号研究 | 忠实于执行的验证 |

两者都返回 `BacktestResult`，因此你可以用同一策略分别跑两个引擎并直接对比。

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

:::caution[据此解读结果]
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
