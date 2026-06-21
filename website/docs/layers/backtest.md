---
title: Backtest
---

# Backtest — `super_trade.backtest`

`super-trade` has **two backtest engines** that take the *same* `Strategy` but
compute results in fundamentally different ways: a fast **vectorized** engine
(`VectorizedEngine`) for signal research, and a faithful **event-driven** engine
(`EventDrivenBacktest`) for execution-sensitive logic. Both reuse the layers below —
signals from `metrics`, stats from `metrics.summary`, charts from `viz`, real bars
from `DataStore` — and both return a `BacktestResult`.

```python
from super_trade.backtest import VectorizedEngine, SmaCross

bars = store.read_bars("600519", Interval.DAY)
result = VectorizedEngine().run(bars, SmaCross(10, 30))
print(result.stats())          # sharpe, cagr, max_drawdown, calmar, ...
result.equity_curve().show()   # Plotly figure via viz
```

## Vectorized vs event-driven

This is the most important concept to grasp. The two engines answer different
questions.

### Vectorized — compute the whole thing at once

`VectorizedEngine` treats a backtest like a **spreadsheet**: it builds whole
**columns** with array math (Polars), with **no Python loop over bars**.

1. the strategy produces a **target weight for every bar at once** —
   `Strategy.positions()` is a Polars expression;
2. it **lags** that column one bar (`shift(1)`) so you trade on the *next* bar — that
   is how it avoids lookahead;
3. it multiplies the held weight by each bar's return, subtracts costs, and takes a
   cumulative product → the equity curve.

Because it is all column operations, it runs in microseconds over years of data.
The trade-off: it assumes you can **always hit the target weight exactly**, with
infinitely divisible capital, and it keeps **no evolving state**. So it cannot model
anything that depends on the *path* — your actual cash, integer 手/lots, or a
**stop-loss** that fires from your real entry price.

→ Use it for **fast signal research**: "does this rule have an edge, after costs?"

### Event-driven — step through time, react to state

`EventDrivenBacktest` does what real trading does: it **loops bar-by-bar**, and at
each step a **broker + risk manager react to the current state** — your cash, your
positions, the price right now — and decide orders. At each bar it:

1. marks the account to market;
2. checks **stop-losses** against each holding's actual entry price → sells if breached;
3. evaluates the strategy's signal → sizes a buy with the **cash and lots you actually
   have**;
4. fills orders through the `SimBroker`, updating cash and positions.

Because it carries **evolving state** and makes **sequential decisions**, it models
what the vectorized engine can't: stop-loss, real cash / board-lot limits, per-name
sizing. It is slower (a Python loop), but faithful — and the **same loop drives live
trading** (swap `SimBroker` for `QmtBroker`).

→ Use it to **validate execution-sensitive logic** (especially the stop-loss) before
going live.

### Side by side

| | Vectorized (`VectorizedEngine`) | Event-driven (`EventDrivenBacktest`) |
|---|---|---|
| How it computes | whole columns at once (no loop) | bar-by-bar loop |
| State | none (assumes target weight always hit) | evolving account: cash + share positions |
| Speed | very fast | slower |
| Stop-loss / cash / lots | ❌ can't model | ✅ modelled |
| Same code path as live? | no | yes (shares the broker + risk loop) |
| Use for | fast signal research | execution-faithful validation |

Both return a `BacktestResult`, so you can run the same strategy through each and
compare directly.

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

:::caution[Interpret results accordingly]
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
