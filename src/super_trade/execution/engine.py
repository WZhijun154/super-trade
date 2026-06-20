"""Execution engine — turns strategy signals into orders, with risk checks.

One ``scan_once()`` is a single sweep of the universe:

1. read recent bars per symbol, evaluate the strategy's target weight + the price
2. mark the account to market; apply the daily-loss halt
3. **stop-loss exits** first (risk before reward)
4. **signal entries/exits**, sized by the :class:`RiskManager`
5. submit orders through the broker (or just log them, in dry-run)

It is broker-agnostic: pass a ``SimBroker`` to dry-run/backtest, or a
``QmtBroker`` to trade a live (simulation) account. ``dry_run=True`` (default)
never sends an order — it only logs what it would do.
"""

from __future__ import annotations

import time

import logfire

from super_trade.backtest.strategy import Strategy
from super_trade.data import DataStore, Interval

from .broker import Broker, Fill, Order, Side
from .risk import RiskManager


class ExecutionEngine:
    """Scan the universe and trade a strategy through a broker."""

    def __init__(
        self,
        broker: Broker,
        store: DataStore,
        strategy: Strategy,
        risk: RiskManager,
        *,
        universe: list[str] | None = None,
        interval: Interval = Interval.DAY,
        lookback: int = 250,
        dry_run: bool = True,
    ) -> None:
        self._broker = broker
        self._store = store
        self._strategy = strategy
        self._risk = risk
        self._universe = universe
        self._interval = interval
        self._lookback = lookback
        self._dry_run = dry_run

    def _universe_symbols(self) -> list[str]:
        return self._universe or self._store.list_symbols(self._interval)

    def _price_and_target(self, symbol: str) -> tuple[float, float] | None:
        bars = self._store.read_bars(symbol, self._interval)
        if bars.height == 0:
            return None
        bars = bars.tail(self._lookback).with_columns(
            self._strategy.positions().alias("_target")
        )
        price = bars["close"][-1]
        target = bars["_target"][-1]
        target = 0.0 if target is None else float(target)
        return float(price), target

    def scan_once(self) -> list[Fill]:
        """Run a single scan of the universe; return the fills produced."""
        with logfire.span("execution_scan", dry_run=self._dry_run):
            prices: dict[str, float] = {}
            targets: dict[str, float] = {}
            for symbol in self._universe_symbols():
                pt = self._price_and_target(symbol)
                if pt is None:
                    continue
                prices[symbol], targets[symbol] = pt

            equity = self._broker.cash() + sum(
                pos.shares * prices.get(sym, pos.avg_price)
                for sym, pos in self._broker.positions().items()
            )
            if self._risk.update_daily_loss(equity):
                logfire.warn("daily loss halt active; skipping new entries")

            fills: list[Fill] = []
            stopped: set[str] = set()
            # 1) stop-loss exits — always allowed, even when halted
            for symbol, pos in list(self._broker.positions().items()):
                price = prices.get(symbol)
                if price is not None and self._risk.stop_triggered(pos, price):
                    stopped.add(symbol)
                    fill = self._submit(
                        Order(symbol, Side.SELL, pos.shares, price, reason="stop_loss")
                    )
                    if fill:
                        fills.append(fill)

            # 2) signal-driven entries/exits (skip names just stopped out)
            for symbol, target in targets.items():
                if symbol in stopped:
                    continue
                held = self._broker.shares(symbol)
                price = prices[symbol]
                if target > 0 and held == 0 and self._risk.can_trade():
                    shares = self._risk.max_buy_shares(
                        symbol, price, equity, self._broker
                    )
                    if shares > 0:
                        fill = self._submit(
                            Order(symbol, Side.BUY, shares, price, reason="signal")
                        )
                        if fill:
                            fills.append(fill)
                elif target <= 0 and held > 0:
                    fill = self._submit(
                        Order(symbol, Side.SELL, held, price, reason="signal_exit")
                    )
                    if fill:
                        fills.append(fill)

            logfire.info("scan complete", symbols=len(prices), orders=len(fills))
            return fills

    def run(self, interval_seconds: int = 10, max_scans: int | None = None) -> None:
        """Scan every ``interval_seconds`` (default 10s). Blocks; Ctrl-C to stop.

        ``max_scans`` bounds the loop (useful for testing); ``None`` runs forever.
        """
        equity = self._broker.cash()
        self._risk.start_day(equity)
        scans = 0
        while max_scans is None or scans < max_scans:
            try:
                self.scan_once()
            except Exception as exc:  # keep the loop alive; surface the error
                logfire.error("scan failed: {error}", error=str(exc))
            scans += 1
            if max_scans is not None and scans >= max_scans:
                break
            time.sleep(interval_seconds)

    def _submit(self, order: Order) -> Fill | None:
        # The halt / order cap blocks new BUYS only; exits (sells, stop-loss) must
        # always be allowed to go through.
        if order.side == Side.BUY and not self._risk.can_trade():
            return None
        if self._dry_run:
            logfire.warn(
                "DRY-RUN {side} {shares} {symbol} @ {price} ({reason})",
                side=order.side.value,
                shares=order.shares,
                symbol=order.symbol,
                price=order.price,
                reason=order.reason,
            )
            self._risk.record_order()
            return None
        fill = self._broker.place_order(order)
        self._risk.record_order()
        if fill is None:
            logfire.warn("order rejected: {symbol}", symbol=order.symbol)
        else:
            logfire.info(
                "filled {side} {shares} {symbol} @ {price}",
                side=order.side.value,
                shares=order.shares,
                symbol=order.symbol,
                price=order.price,
            )
        return fill
