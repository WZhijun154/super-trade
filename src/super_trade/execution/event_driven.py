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
from super_trade.data import DataStore, Interval, load_bars

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
        resample_from: Interval | None = None,
    ) -> None:
        self._store = store
        self._strategy = strategy
        self._cash = cash
        self._costs = costs or CostModel()
        self._risk = risk or RiskManager()
        self._universe = universe
        self._interval = interval
        # When set (e.g. Interval.MINUTE), bars are read at this base granularity
        # and resampled to `interval` — the "system on 1-minute data" path.
        self._resample_from = resample_from

    def run(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> BacktestResult:
        # A fresh simulated account for this run: starting cash + the cost model.
        # All fills, cash, and positions live inside this broker.
        broker = SimBroker(cash=self._cash, costs=self._costs)
        risk = self._risk
        # Default to every symbol in the store if no explicit universe was given.
        universe = self._universe or self._store.list_symbols(self._interval)

        # ---- Phase 1: pre-load data and precompute signals --------------------
        # For each symbol we build a lookup: timestamp -> (close_price, target).
        # We precompute the strategy's target weight ONCE over the full window;
        # this is valid (no lookahead) because indicators are *causal* — each
        # value at bar t only uses data up to t. Doing it up front means the
        # per-bar loop below is a cheap dict lookup, not a re-evaluation.
        bars_by_symbol: dict[str, dict[datetime, tuple[float, float]]] = {}
        # The union of every symbol's bar timestamps becomes the simulation clock.
        timestamps: set[datetime] = set()
        for symbol in universe:
            bars = load_bars(
                self._store,
                symbol,
                self._interval,
                start,
                end,
                resample_from=self._resample_from,
            )
            if bars.height == 0:
                continue  # no data for this symbol in the window — skip it
            # Add the strategy's target-weight column alongside the OHLCV columns.
            bars = bars.with_columns(self._strategy.positions().alias("target"))
            # Flatten the frame into a {timestamp: (close, target)} dict for O(1)
            # access during the loop.
            row_map: dict[datetime, tuple[float, float]] = {}
            for row in bars.iter_rows(named=True):
                target = row["target"]
                row_map[row["timestamp"]] = (
                    float(row["close"]),
                    # target can be null during an indicator's warm-up → treat as 0
                    0.0 if target is None else float(target),
                )
            bars_by_symbol[symbol] = row_map
            timestamps.update(row_map)  # collect this symbol's timestamps

        # ---- Phase 2: step through time, bar by bar ---------------------------
        timeline = sorted(timestamps)  # chronological order — the "clock"
        last_price: dict[str, float] = {}  # most recent known close per symbol
        equity_rows: list[dict] = []  # one equity snapshot per timestamp
        current_date = None  # tracks day boundaries for the risk reset

        for ts in timeline:
            # Risk limits like the daily-loss halt and order count are per *day*.
            # When the calendar day changes, snapshot the day's opening equity and
            # reset those counters (and clear any prior halt).
            if ts.date() != current_date:
                current_date = ts.date()
                risk.start_day(self._equity(broker, last_price))

            # Mark prices forward: any symbol that has a bar at this timestamp
            # gets its latest close; symbols that didn't trade keep their old price.
            for symbol, row_map in bars_by_symbol.items():
                if ts in row_map:
                    last_price[symbol] = row_map[ts][0]

            # Mark the whole account to market at the current prices, then let the
            # risk manager check whether the daily-loss limit is now breached.
            equity = self._equity(broker, last_price)
            risk.update_daily_loss(equity)

            # 1) Stop-loss exits run FIRST (risk before reward). For every open
            #    position, if the price has fallen past its stop, sell it all.
            #    `stopped` records these so we don't re-buy the same name this bar.
            stopped: set[str] = set()
            for symbol, pos in list(broker.positions().items()):
                price = last_price.get(symbol)
                if price is not None and risk.stop_triggered(pos, price):
                    broker.place_order(
                        Order(symbol, Side.SELL, pos.shares, price, reason="stop_loss")
                    )
                    stopped.add(symbol)

            # 2) Signal-driven entries/exits, only for symbols trading right now.
            for symbol, row_map in bars_by_symbol.items():
                # Skip symbols with no bar at this timestamp, or just stopped out.
                if ts not in row_map or symbol in stopped:
                    continue
                price, target = row_map[ts]
                held = broker.shares(symbol)  # shares currently held (0 if none)
                if target > 0 and held == 0 and risk.can_trade():
                    # Want long, currently flat, and trading is allowed → size a
                    # buy within per-name / gross / cash limits and submit it.
                    shares = risk.max_buy_shares(symbol, price, equity, broker)
                    if shares > 0:
                        broker.place_order(
                            Order(symbol, Side.BUY, shares, price, reason="signal")
                        )
                elif target <= 0 and held > 0:
                    # Want flat (or short) but currently long → sell the whole
                    # position. (Exits are always allowed, even when halted.)
                    broker.place_order(
                        Order(symbol, Side.SELL, held, price, reason="signal_exit")
                    )

            # Record the post-trade equity + cash for this timestamp; this list
            # becomes the equity curve.
            equity_rows.append(
                {
                    "timestamp": ts,
                    "equity": self._equity(broker, last_price),
                    "cash": broker.cash(),
                }
            )

        # ---- Phase 3: assemble the result -------------------------------------
        # Turn the per-bar snapshots into a DataFrame and wrap it in a
        # BacktestResult, which computes stats (via metrics.summary on `equity`)
        # and charts (via viz) — the same API the vectorized engine returns.
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
