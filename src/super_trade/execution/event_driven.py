"""Event-driven backtest — replay history through the SimBroker.

Where the vectorized backtester computes P&L over the whole frame at once, this
steps through bars **chronologically**, running the same scan logic the live
engine uses (stop-loss, risk-sized orders, real cash/lots) at each bar. That makes
it able to model the **path-dependent** behaviour the vectorized engine cannot —
most importantly the **stop-loss** — so you can validate it before going live.

It lives in ``execution`` (not ``backtest``) because it depends on the execution
layer's ``SimBroker`` and ``RiskManager``; it reuses ``backtest.BacktestResult`` for
stats and charts.

The strategy's target column is precomputed once over the full window (valid —
indicators are causal, backward-looking only), then **lagged one bar**: a signal
formed on bar *t*'s close is executed at *t+1*'s **open**, never at the close that
produced it. Stop-losses trigger **intrabar** (on the bar's low) and fill at the stop
price — or the gap-down open if the bar opened through it. This matches the
vectorized engine's one-bar lag, so the two tiers are comparable.

On top of that it applies A-share **market** rules (``MarketRules``, default on),
so an order that wouldn't have filled in reality doesn't fill here:

* **T+1** — shares bought today can't be sold until the next trading day.
* **涨跌停** — can't BUY at the upper limit or SELL at the lower limit (band by board).
* **停牌** — a bar with no volume (or no bar) doesn't trade.
* **partial fills** — an order takes at most a fraction of the bar's volume.
"""

from __future__ import annotations

import math
from datetime import date, datetime

import polars as pl

from super_trade.backtest.costs import CostModel
from super_trade.backtest.result import BacktestResult
from super_trade.backtest.strategy import Strategy
from super_trade.data import DataStore, Interval, load_bars

from .broker import LOT_SIZE, Order, Side
from .market import MarketRules, limit_pct
from .risk import RiskManager
from .sim_broker import SimBroker


class EventDrivenBacktest:
    """Replay a strategy bar-by-bar over a universe, with realistic execution.

    Unlike the vectorized engine (which computes P&L over the whole price frame at
    once), this advances a simulation clock — the sorted union of every symbol's bar
    timestamps — and at each tick drives the *same* ``SimBroker`` + ``RiskManager``
    the live engine uses. That makes it the tier that models **path-dependent**
    behaviour the vectorized engine cannot: stop-loss exits, a finite cash budget,
    integer 手/lot rounding, per-name position caps, and the daily-loss halt.

    Each bar it **rebalances toward the strategy's target weight** (the signal is a
    fraction of equity, not a 0/1 flag): it sizes the desired position and trades
    only the difference, so a changing target scales a name in and out over many
    bars rather than flipping fully on/off.

    On top of the account mechanics it also models A-share *market* rules via
    ``MarketRules`` (default on): **T+1** (no selling today's buys), **涨跌停**
    price limits, **停牌** suspension, and a volume-based partial-fill cap — so an
    order that wouldn't have filled in reality doesn't fill here either.

    One run is one ``run()`` call: each call builds a *fresh* account, so an instance
    is reusable and stateless between runs. The strategy's target weights are
    precomputed once over the full window (valid because indicators are causal —
    backward-looking only), then the per-bar loop is a cheap dict lookup.

    Construction only stores configuration; no data is read until ``run()``.
    """

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
        rules: MarketRules | None = None,
        weights: dict[str, float] | None = None,
        weight_schedule: list[tuple[date, dict[str, float]]] | None = None,
    ) -> None:
        """Configure a run (nothing is read or simulated until ``run()``).

        Args:
            store: Source of bars. ``run()`` reads real OHLCV from it per symbol;
                also supplies the default universe via ``list_symbols(interval)``.
            strategy: The ``Strategy`` whose ``positions()`` expr yields the per-bar
                **target weight** per symbol — the fraction of equity to hold (0 =
                flat, 1.0 = full, clamped to the per-name cap). Each bar rebalances
                toward it, so fractional and changing weights scale a position in
                and out over time, not just flip it fully on/off.
            cash: Starting cash of the simulated account, in CNY. Caps how much can
                actually be bought regardless of target weights.
            costs: A-share cost model (commission, sell-side stamp tax, slippage)
                charged on every fill. Defaults to ``CostModel()``.
            risk: Position sizing and safety limits — per-name/gross caps, stop-loss,
                daily-loss halt, order count. Defaults to ``RiskManager()`` (limits on).
            universe: Symbols to trade. ``None`` means every symbol the store holds
                at ``interval``. A single-symbol list restricts to that name.
            interval: Bar granularity the simulation steps through (the clock's tick).
            resample_from: When set (e.g. ``Interval.MINUTE``), bars are read at this
                finer granularity and resampled up to ``interval`` on the way in — the
                "system on 1-minute data" path. ``None`` reads ``interval`` directly.
            rules: A-share market realism (T+1, price limits, suspension, partial
                fills). Defaults to ``MarketRules()`` (all on). Pass a relaxed one to
                disable any of them.
            weights: Optional portfolio **budget** per symbol (e.g. from an
                ``Allocator``). The per-bar target becomes ``signal * weight`` — the
                strategy times each name, the weight caps its share of the book.
                ``None`` (or a missing symbol) → weight 1.0 = signal used as-is.
            weight_schedule: Optional **time-varying** budgets for periodic rebalance
                — a date-sorted list of ``(effective_date, {symbol: weight})``. At
                each bar the active entry is the latest one whose date has passed; a
                symbol absent from it gets budget **0** (so a name dropped at a
                rebalance is scaled out). Before the first date, everything is flat.
                Takes precedence over ``weights``. Build one with
                ``super_trade.portfolio.periodic_schedule``.
        """
        self._store = store
        self._strategy = strategy
        self._cash = cash
        self._costs = costs or CostModel()
        self._risk = risk or RiskManager()
        self._rules = rules or MarketRules()
        self._weights = weights or {}  # static per-name budget (default 1.0 each)
        # Periodic budgets: date-sorted (effective_date, weights); overrides _weights.
        self._schedule = (
            sorted(weight_schedule, key=lambda e: e[0]) if weight_schedule else []
        )
        self._lot = LOT_SIZE  # board lot (100 shares); fills round down to this
        self._universe = universe
        self._interval = interval
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
        # For each symbol we build a lookup: timestamp -> (open, close, volume,
        # signal). We precompute the strategy's target weight ONCE over the full
        # window; this is valid (no lookahead) because indicators are *causal* —
        # each value at bar t only uses data up to t. Doing it up front means the
        # per-bar loop below is a cheap dict lookup, not a re-evaluation.
        #
        # NO-LOOKAHEAD ENTRY: we lag the target by one bar (`shift(1)`) and act
        # on it at the NEXT bar's OPEN — the standard retail convention. A signal
        # formed from bar t's close is therefore traded at t+1's open, never at
        # the same close that produced it. `signal` below is that lagged target.
        # `volume` caps partial fills; `low` lets a stop trigger intrabar (below).
        bars_by_symbol: dict[
            str, dict[datetime, tuple[float, float, float, float, float]]
        ] = {}
        # The union of every symbol's bar timestamps becomes the simulation clock.
        timestamps: set[datetime] = set()
        # OHLCV per symbol, kept for the Foxglove candlestick (/bars) export.
        bar_frames: list[pl.DataFrame] = []
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
            bar_frames.append(
                bars.select(
                    "symbol", "timestamp", "open", "high", "low", "close", "volume"
                )
            )
            # Target weight alongside OHLCV, then lag it one bar so this bar acts
            # on the *previous* bar's decision (executed at this bar's open).
            bars = bars.with_columns(self._strategy.positions().alias("target"))
            bars = bars.with_columns(pl.col("target").shift(1).alias("signal"))
            # Flatten into {ts: (open, low, close, volume, signal)} for O(1) access.
            row_map: dict[datetime, tuple[float, float, float, float, float]] = {}
            for row in bars.iter_rows(named=True):
                signal = row["signal"]
                # null (first bar / warm-up) or NaN (a strategy dividing through an
                # undefined indicator) → treat as flat, so sizing never sees a NaN.
                if signal is None or math.isnan(signal):
                    signal = 0.0
                row_map[row["timestamp"]] = (
                    float(row["open"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row["volume"]),
                    float(signal),
                )
            bars_by_symbol[symbol] = row_map
            timestamps.update(row_map)  # collect this symbol's timestamps

        # ---- Phase 2: step through time, bar by bar ---------------------------
        timeline = sorted(timestamps)  # chronological order — the "clock"
        last_price: dict[str, float] = {}  # most recent known close per symbol
        equity_rows: list[dict] = []  # one equity snapshot per timestamp
        current_date = None  # tracks day boundaries for per-day resets
        # T+1 ledger: shares bought *today* per symbol (can't be sold until tmrw).
        bought_today: dict[str, int] = {}
        # Limit reference: each symbol's close from the *previous* trading day,
        # used to compute today's 涨跌停 band.
        prev_ref_close: dict[str, float] = {}
        # Periodic-rebalance state: index into self._schedule + the active budgets.
        sched_idx = -1
        active_budget: dict[str, float] = {}
        # Telemetry: per-bar snapshot of open positions (for the Foxglove exporter).
        position_rows: list[dict] = []

        for ts in timeline:
            broker.set_time(ts)  # stamp this bar's fills with its timestamp
            # Risk limits, the T+1 ledger and the limit reference are per *day*.
            # When the calendar day changes: snapshot yesterday's closes as the
            # limit reference, clear today's T+1 ledger, and reset the risk
            # counters (`last_price` still holds the prior day's closes here,
            # because we haven't marked today's bars yet).
            if ts.date() != current_date:
                current_date = ts.date()
                prev_ref_close = dict(last_price)
                bought_today = {}
                risk.start_day(self._equity(broker, last_price))
                # Advance the rebalance schedule to the latest budget now in effect.
                while (
                    sched_idx + 1 < len(self._schedule)
                    and self._schedule[sched_idx + 1][0] <= current_date
                ):
                    sched_idx += 1
                if self._schedule:
                    active_budget = (
                        self._schedule[sched_idx][1] if sched_idx >= 0 else {}
                    )

            # Mark prices forward: any symbol that has a bar at this timestamp
            # gets its latest close (index [2]); symbols that didn't trade keep
            # their old price. Close is the mark-to-market reference.
            for symbol, row_map in bars_by_symbol.items():
                if ts in row_map:
                    last_price[symbol] = row_map[ts][2]

            # Mark the whole account to market at the current prices, then let the
            # risk manager check whether the daily-loss limit is now breached.
            equity = self._equity(broker, last_price)
            risk.update_daily_loss(equity)

            # 1) Stop-loss exits run FIRST (risk before reward). The stop triggers
            #    INTRABAR — on the bar's LOW, so it fires even if the close recovers
            #    above the level — and fills at the stop price, or worse at the OPEN
            #    if the bar gapped below it (`min(open, stop_price)`). `stopped`
            #    marks the name so we never re-buy something we're exiting this bar.
            #    Market rules can still block/partial the exit (停牌/跌停, or shares
            #    bought today under T+1 leave you trapped).
            stopped: set[str] = set()
            for symbol, pos in list(broker.positions().items()):
                bar = bars_by_symbol[symbol].get(ts)
                if bar is None:
                    continue  # 停牌 / no bar today → can't exit, position trapped
                open_px, low, _close, volume, _signal = bar
                if not risk.stop_triggered(pos, low):  # low breached the stop level?
                    continue
                stopped.add(symbol)
                # Fill at the stop level, or at the open if the bar gapped below it.
                fill_price = min(open_px, risk.stop_price(pos))
                qty = self._exitable(pos.shares, symbol, bought_today, volume)
                if qty > 0 and self._tradable(
                    symbol, Side.SELL, fill_price, volume, prev_ref_close.get(symbol)
                ):
                    broker.place_order(
                        Order(
                            symbol,
                            Side.SELL,
                            qty,
                            fill_price,
                            reason="stop_loss",
                            participation=self._participation(qty, volume),
                        )
                    )

            # 2) Rebalance each symbol toward its TARGET WEIGHT. `signal` is the
            #    strategy's desired weight (lagged one bar): the fraction of equity
            #    to hold in this name, not a 0/1 in-or-out flag. We turn it into a
            #    target share count and trade only the *difference* vs what we hold
            #    — so a rising target scales IN over several bars and a falling one
            #    scales OUT, trading the same name repeatedly. Fills are at THIS
            #    bar's OPEN (t+1-open), so no trade uses the close that set it.
            for symbol, row_map in bars_by_symbol.items():
                # Skip symbols with no bar at this timestamp, or just stopped out.
                if ts not in row_map or symbol in stopped:
                    continue
                open_px, _low, _close, volume, signal = row_map[ts]
                prev_close = prev_ref_close.get(symbol)
                held = broker.shares(symbol)  # shares currently held (0 if none)
                # Target weight = signal (timing) * portfolio budget (allocation),
                # then clamped to [0, per-name cap]. Convert to a lot-aligned share
                # target against equity and trade only the delta. The budget comes
                # from the active rebalance schedule (deselected name → 0 → scaled
                # out); else the static `weights` (default 1.0 = signal as-is).
                if self._schedule:
                    budget = active_budget.get(symbol, 0.0)
                else:
                    budget = self._weights.get(symbol, 1.0)
                weight = min(max(signal * budget, 0.0), risk.limits.max_position_weight)
                desired = self._target_shares(weight, equity, open_px)
                delta = desired - held  # >0 buy more, <0 sell some, 0 already there
                if delta > 0 and risk.can_trade():
                    # Scale IN: buy the shortfall, but no more than cash/gross/cap
                    # room and the bar's participation volume, and only if the buy
                    # isn't blocked by 停牌/涨停. (New buys are blocked when halted.)
                    buyable = min(
                        delta, risk.max_buy_shares(symbol, open_px, equity, broker)
                    )
                    cap = self._volume_cap(volume)
                    if cap is not None:
                        buyable = min(buyable, cap)
                    if buyable > 0 and self._tradable(
                        symbol, Side.BUY, open_px, volume, prev_close
                    ):
                        fill = broker.place_order(
                            Order(
                                symbol,
                                Side.BUY,
                                buyable,
                                open_px,
                                reason="rebalance",
                                participation=self._participation(buyable, volume),
                            )
                        )
                        if fill is not None:  # record T+1: these can't sell today
                            bought_today[symbol] = (
                                bought_today.get(symbol, 0) + fill.shares
                            )
                elif delta < 0:
                    # Scale OUT: sell the excess (-delta), capped by T+1-sellable
                    # shares and the volume cap, if 停牌/跌停 doesn't block it.
                    # (Exits are allowed even when halted.) Unsold excess rolls over.
                    sellable = self._exitable(held, symbol, bought_today, volume)
                    qty = min(-delta, sellable)
                    if qty > 0 and self._tradable(
                        symbol, Side.SELL, open_px, volume, prev_close
                    ):
                        broker.place_order(
                            Order(
                                symbol,
                                Side.SELL,
                                qty,
                                open_px,
                                reason="rebalance",
                                participation=self._participation(qty, volume),
                            )
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
            # Telemetry: snapshot each open position at this bar (Foxglove export).
            for sym, pos in broker.positions().items():
                price = last_price.get(sym, pos.avg_price)
                position_rows.append(
                    {
                        "timestamp": ts,
                        "symbol": sym,
                        "shares": pos.shares,
                        "avg_price": pos.avg_price,
                        "price": price,
                        "market_value": pos.shares * price,
                        "unrealized_pnl": pos.shares * (price - pos.avg_price),
                    }
                )

        # ---- Phase 3: assemble the result -------------------------------------
        # Turn the per-bar snapshots into a DataFrame and wrap it in a
        # BacktestResult, which computes stats (via metrics.summary on `equity`)
        # and charts (via viz) — the same API the vectorized engine returns.
        # `fills` and `positions` carry the per-trade / per-bar telemetry the
        # Foxglove MCAP exporter streams.
        data = pl.DataFrame(
            equity_rows,
            schema={"timestamp": pl.Datetime, "equity": pl.Float64, "cash": pl.Float64},
        )
        return BacktestResult(
            data,
            strategy_name=f"{self._strategy.name} (event-driven)",
            fills=self._fills_frame(broker),
            positions=pl.DataFrame(position_rows) if position_rows else None,
            bars=pl.concat(bar_frames) if bar_frames else None,
        )

    @staticmethod
    def _fills_frame(broker: SimBroker) -> pl.DataFrame | None:
        """Broker fills as a DataFrame (timestamp, symbol, side, shares, …)."""
        if not broker.fills:
            return None
        return pl.DataFrame(
            [
                {
                    "timestamp": f.timestamp,
                    "symbol": f.symbol,
                    "side": str(f.side),
                    "shares": f.shares,
                    "price": f.price,
                    "cost": f.cost,
                    "notional": f.shares * f.price,
                    "reason": f.reason,
                }
                for f in broker.fills
            ]
        )

    @staticmethod
    def _equity(broker: SimBroker, prices: dict[str, float]) -> float:
        """Mark-to-market account value: cash + every position at current prices.

        This is the broker's total net worth at one instant — the number that
        becomes the equity curve and feeds the risk manager's daily-loss check.

        Args:
            broker: The simulated account (its ``cash()`` and open ``positions()``).
            prices: Latest price per symbol (the bar's close). A symbol missing
                from this map — e.g. it hasn't traded yet this run — falls back to
                its ``avg_price`` (entry cost), which marks it flat (no unrealised
                P&L) rather than crashing on a missing key.

        Returns:
            Cash plus the summed market value (``shares * price``) of all holdings.
        """
        return broker.cash() + sum(
            pos.shares * prices.get(sym, pos.avg_price)
            for sym, pos in broker.positions().items()
        )

    def _target_shares(self, weight: float, equity: float, price: float) -> int:
        """Lot-aligned share count for holding ``weight`` of ``equity`` at ``price``.

        ``weight`` is a fraction of equity (already clamped to ``[0, per-name cap]``).
        Rounds to the **nearest** whole board lot — the ±half-lot tolerance is a
        deadband that stops a steady target from churning a lot back and forth as
        equity wobbles across a boundary each bar. (Buys are still hard-capped by
        ``max_buy_shares``, so rounding up can never breach the per-name cap.)
        """
        if price <= 0 or weight <= 0:
            return 0
        return int(weight * equity / price / self._lot + 0.5) * self._lot

    @staticmethod
    def _participation(shares: int, volume: float) -> float:
        """Order size as a fraction of the bar's volume (drives market impact)."""
        return shares / volume if volume > 0 else 0.0

    def _volume_cap(self, volume: float) -> int | None:
        """Max lot-aligned shares one order may take this bar (participation cap).

        Returns ``None`` when the cap is disabled (``participation_rate <= 0``) —
        callers then treat the fill as unconstrained by volume.
        """
        rate = self._rules.participation_rate
        if rate <= 0:
            return None
        return int(volume * rate) // self._lot * self._lot

    def _exitable(
        self,
        held: int,
        symbol: str,
        bought_today: dict[str, int],
        volume: float,
    ) -> int:
        """Shares of ``held`` that may be sold this bar, after T+1 + the volume cap.

        T+1 removes shares bought *today* (``bought_today``); the participation cap
        then limits the rest to a fraction of the bar's volume. Result is
        lot-aligned and never negative; 0 means "can't exit this bar".
        """
        sellable = held
        if self._rules.t_plus_1:
            sellable = max(0, held - bought_today.get(symbol, 0))
        cap = self._volume_cap(volume)
        return sellable if cap is None else min(sellable, cap)

    def _tradable(
        self,
        symbol: str,
        side: Side,
        price: float,
        volume: float,
        prev_close: float | None,
    ) -> bool:
        """Whether an order of ``side`` could fill at ``price`` on this bar.

        Blocks two A-share conditions: **停牌** (a bar with no volume doesn't
        trade) and **涨跌停** (at the upper limit there are no sellers, so you
        can't BUY; at the lower limit no buyers, so you can't SELL). The limit
        band comes from :func:`limit_pct` (board-specific) applied to the previous
        day's close; it's skipped when there's no reference close yet (first day).
        """
        rules = self._rules
        if rules.enforce_suspension and volume <= 0:
            return False  # 停牌 / no trades printed this bar
        if rules.enforce_price_limits and prev_close is not None:
            pct = limit_pct(symbol, rules.default_limit_pct)
            if side is Side.BUY and price >= round(prev_close * (1 + pct), 2):
                return False  # 涨停 — locked up, no one will sell to you
            if side is Side.SELL and price <= round(prev_close * (1 - pct), 2):
                return False  # 跌停 — locked down, no one will buy from you
        return True
