---
title: Backtest
---

# Backtest — `super_trade.backtest`

A **vectorized** engine: a strategy emits target weights as a Polars expression,
and P&L is computed across the whole frame at once. It reuses every layer below it
— signals from `metrics`, stats from `metrics.summary`, charts from `viz`, real
bars from `DataStore`.

```python
from super_trade.backtest import VectorizedEngine, SmaCross

bars = store.read_bars("600519", Interval.DAY)
result = VectorizedEngine().run(bars, SmaCross(10, 30))
print(result.stats())          # sharpe, cagr, max_drawdown, calmar, ...
result.equity_curve().show()   # Plotly figure via viz
```

## Strategy

```python
class Strategy(ABC):
    name: str
    def positions(self) -> pl.Expr: ...   # target weight per bar
```

Target weight: `1.0` = fully long, `0` = flat, negative = short. Examples:
`BuyAndHold`, `SmaCross(fast, slow)`, `RsiReversion(window, low, high)` — each built
on `metrics`.

## The hard parts, handled

- **No lookahead** — the engine holds `target.shift(1)`: you decide on bar *t*'s
  close and trade into the position on *t+1*. Enforced by the engine, not the
  strategy.
- **A-share costs** — `CostModel` charges commission (both sides), **stamp tax on
  sells only** (印花税, asymmetric), and slippage, on turnover.
- **`equity[0] == 1.0`** so the `summary` metrics compute cleanly on the equity
  column.

## Results

`BacktestResult` exposes `stats()` (dict of summary metrics), `trades()` (position
changes), and `equity_curve()` / `drawdown()` (Plotly figures).

## Limitations — what is *not* modeled

The vectorized engine works in **fractional target weights**, one strategy on one
symbol. That keeps it fast and composable, but it **cannot** express the following
real-world frictions:

| Concern | Modeled? | Why / what it needs |
|---|---|---|
| Commission (手续费) / stamp tax (印花税) / slippage (滑点) | ✅ via `CostModel` | charged on turnover; stamp tax is sell-side only |
| **Capital constraints (资金约束)** — cash balance, integer 手/lots, can't buy beyond available cash | ❌ | needs an account model tracking cash + shares |
| **Forced liquidation (被迫清仓)** — margin stop-out | ❌ | path-dependent; needs a sequential loop checking equity each bar |
| **Multi-strategy capital competition (多策略资金竞争)** | ❌ | needs a portfolio allocating one capital pool across strategies |

The last three are **portfolio-level and path-dependent** — structurally out of
reach for a vectorized weight engine, which assumes you can always hit the target
weight with infinitely divisible capital and computes the whole series at once.

:::caution Interpret results accordingly
Treat vectorized results as **signal research** — "does the edge exist, after
costs?" — not as a faithful simulation of trading the strategy with real money.
:::

## Event-driven backtest

`execution.EventDrivenBacktest` is the second tier. It replays history **bar-by-bar**
through the execution layer's `SimBroker` + `RiskManager` — the same machinery that
trades live — so it models the **path-dependent** behaviour the vectorized engine
can't: the **stop-loss**, plus real cash, integer 手/lots, and per-name sizing
(capital constraints). It lives in [`execution`](./execution) because it depends on
the broker; it reuses `BacktestResult` for stats and charts.

```python
from super_trade.execution import EventDrivenBacktest, RiskManager, RiskLimits

result = EventDrivenBacktest(
    store, SmaCross(10, 30), cash=1_000_000, universe=["600519"],
    risk=RiskManager(RiskLimits(stop_loss=0.08)),
).run()
print(result.stats())          # same BacktestResult API as the vectorized run
result.equity_curve().show()
```

The strategy's target column is precomputed once over the window — valid (no
lookahead) because indicators are causal. This is the tier to **validate a
stop-loss before running it live**: on the sandbox, an 8% stop cut max drawdown
from −23.5% to −4.8% versus the vectorized run.

Still vectorized-only / future: portfolio capital allocation across **multiple**
strategies (多策略资金竞争), margin/forced liquidation, and cross-sectional weights
via `.over("symbol")`.
