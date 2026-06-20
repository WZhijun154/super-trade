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

They require the planned **event-driven tier**: an `Account` (cash + positions in
real shares), a `Broker` (fills orders against cash/lots/margin and triggers forced
liquidation), and a `Portfolio` (allocates one capital pool across strategies).

:::caution Interpret results accordingly
Treat vectorized results as **signal research** — "does the edge exist, after
costs?" — not as a faithful simulation of trading the strategy with real money.
:::

## Roadmap

Portfolio / cross-sectional backtests (weights per symbol via `.over("symbol")`),
an **event-driven engine** (Account / Broker / Portfolio) covering the limitations
above, and a dashboard backtest page.
