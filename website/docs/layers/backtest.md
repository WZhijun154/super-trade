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

## Roadmap

Portfolio / cross-sectional backtests (weights per symbol via `.over("symbol")`),
an event-driven engine for path-dependent execution, and a dashboard backtest page.
