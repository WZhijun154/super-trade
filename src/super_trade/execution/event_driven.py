"""Event-driven backtest — replay history through the SimBroker.

Where the vectorized backtester computes P&L over the whole frame at once, this
steps through bars **chronologically**, running the same scan logic the live
engine uses (stop-loss, risk-sized orders, real cash/lots) at each bar. That makes
it able to model the **path-dependent** behaviour the vectorized engine cannot —
most importantly the **stop-loss** — so you can validate it before going live.

It lives in ``execution`` (not ``backtest``) because it depends on the execution
layer's ``SimBroker`` and ``RiskManager``; it reuses ``backtest.BacktestResult`` for
stats and charts.

The strategy's target column is precomputed once over the full window. That is
valid (no lookahead) because indicators are causal — backward-looking only.
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from super_trade.backtest.costs import CostModel
from super_trade.backtest.result import BacktestResult
from super_trade.backtest.strategy import Strategy
from super_trade.data import DataStore, Interval

from .broker import Order, Side
from .risk import RiskManager
from .sim_broker import SimBroker


class EventDrivenBacktest:
    """Replay a strategy bar-by-bar over a universe, with realistic execution."""

    def __init__(
        self,
        store: DataStore,
        strategy: Strategy,
        *,
        cash: float = 1_000_000.0,
        costs: CostModel | None = None,
        risk: RiskManager | None = None,
        universe: list[str] | None = None,
        interval: Interval = Interval.DAY,
    ) -> None:
        self._store = store
        self._strategy = strategy
        self._cash = cash
        self._costs = costs or CostModel()
        self._risk = risk or RiskManager()
        self._universe = universe
        self._interval = interval

    def run(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> BacktestResult:
        broker = SimBroker(cash=self._cash, costs=self._costs)
        risk = self._risk
        universe = self._universe or self._store.list_symbols(self._interval)

        # Pre-load each symbol and precompute the (causal) target column.
        bars_by_symbol: dict[str, dict[datetime, tuple[float, float]]] = {}
        timestamps: set[datetime] = set()
        for symbol in universe:
            bars = self._store.read_bars(symbol, self._interval, start, end)
            if bars.height == 0:
                continue
            bars = bars.with_columns(self._strategy.positions().alias("target"))
            row_map: dict[datetime, tuple[float, float]] = {}
            for row in bars.iter_rows(named=True):
                target = row["target"]
                row_map[row["timestamp"]] = (
                    float(row["close"]),
                    0.0 if target is None else float(target),
                )
            bars_by_symbol[symbol] = row_map
            timestamps.update(row_map)

        timeline = sorted(timestamps)
        last_price: dict[str, float] = {}
        equity_rows: list[dict] = []
        current_date = None

        for ts in timeline:
            if ts.date() != current_date:  # reset intraday risk state each day
                current_date = ts.date()
                risk.start_day(self._equity(broker, last_price))

            # advance prices for symbols that trade at this timestamp
            for symbol, row_map in bars_by_symbol.items():
                if ts in row_map:
                    last_price[symbol] = row_map[ts][0]

            equity = self._equity(broker, last_price)
            risk.update_daily_loss(equity)

            # 1) stop-loss exits first
            stopped: set[str] = set()
            for symbol, pos in list(broker.positions().items()):
                price = last_price.get(symbol)
                if price is not None and risk.stop_triggered(pos, price):
                    broker.place_order(
                        Order(symbol, Side.SELL, pos.shares, price, reason="stop_loss")
                    )
                    stopped.add(symbol)

            # 2) signal entries/exits for symbols trading now
            for symbol, row_map in bars_by_symbol.items():
                if ts not in row_map or symbol in stopped:
                    continue
                price, target = row_map[ts]
                held = broker.shares(symbol)
                if target > 0 and held == 0 and risk.can_trade():
                    shares = risk.max_buy_shares(symbol, price, equity, broker)
                    if shares > 0:
                        broker.place_order(
                            Order(symbol, Side.BUY, shares, price, reason="signal")
                        )
                elif target <= 0 and held > 0:
                    broker.place_order(
                        Order(symbol, Side.SELL, held, price, reason="signal_exit")
                    )

            equity_rows.append(
                {
                    "timestamp": ts,
                    "equity": self._equity(broker, last_price),
                    "cash": broker.cash(),
                }
            )

        data = pl.DataFrame(
            equity_rows,
            schema={"timestamp": pl.Datetime, "equity": pl.Float64, "cash": pl.Float64},
        )
        return BacktestResult(
            data, strategy_name=f"{self._strategy.name} (event-driven)"
        )

    @staticmethod
    def _equity(broker: SimBroker, prices: dict[str, float]) -> float:
        return broker.cash() + sum(
            pos.shares * prices.get(sym, pos.avg_price)
            for sym, pos in broker.positions().items()
        )
