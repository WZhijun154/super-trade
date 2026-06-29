"""Simulated broker — fills orders against an in-memory account.

Used for the event-driven backtest and for dry runs. Enforces cash availability,
board-lot sizing, and the same A-share costs as the vectorized backtester
(reusing ``CostModel``). This is the safe default; no real orders are ever sent.
"""

from __future__ import annotations

from datetime import datetime

from super_trade.backtest.costs import CostModel

from .broker import LOT_SIZE, Account, Broker, Fill, Order, Position, Side


class SimBroker(Broker):
    """An in-memory broker that simulates fills against a cash + positions account.

    This is the backtest/dry-run side of the :class:`Broker` interface; the live
    side is ``QmtBroker``. Code that places orders depends only on ``Broker``, so
    the same strategy + ``RiskManager`` drive a simulated run or a real QMT
    simulation account by swapping the broker.

    **Fill model — deliberately simple.** Each order fills *immediately, in full,
    at its own reference price* (``order.price``); there is no order book, queue,
    slippage curve, or partial fill here. The broker enforces only the two
    constraints that are unconditionally true of any account:

    * **Board lots** — quantity must be a positive whole multiple of ``lot_size``
      (100 shares = 1 手); otherwise the order is rejected.
    * **No naked positions** — a BUY needs ``notional + cost <= cash``; a SELL
      can't exceed shares held. Either shortfall rejects the order (no margin,
      no shorting).

    Everything *market*-shaped (T+1, 涨跌停 price limits, 停牌 suspension, volume
    participation, the t+1-open fill price) lives one layer up in
    :class:`EventDrivenBacktest`, which narrows the order before calling here. Keep
    it that way: this class stays a pure, reusable settlement engine, and the loop
    owns anything that needs the clock, the day, or the bar.

    Costs come from :class:`~super_trade.backtest.costs.CostModel` — the *same*
    model the vectorized engine uses, so both tiers charge commission (with the ¥5
    floor), sell-side stamp tax, transfer fee, and slippage identically.

    State is mutable and lives for one run: ``cash``/``positions`` mutate on every
    fill and ``fills`` accumulates the trade log. Construct a fresh ``SimBroker``
    per backtest (``EventDrivenBacktest.run`` already does).

    Attributes:
        fills: Append-only log of every completed :class:`Fill`, in order — the
            basis for ``daily_report`` and trade-level analysis.
    """

    def __init__(
        self,
        cash: float,
        costs: CostModel | None = None,
        lot_size: int = LOT_SIZE,
    ) -> None:
        """Open a simulated account.

        Args:
            cash: Starting cash in ¥ — the hard ceiling on what can be bought.
            costs: A-share cost model charged on every fill. Defaults to
                ``CostModel()`` (live defaults); pass ``NO_COSTS`` for a
                frictionless run.
            lot_size: Board-lot size in shares (100 for A-shares). Orders must be
                whole multiples of it.
        """
        self._account = Account(cash=cash)
        self._costs = costs or CostModel()
        self._lot = lot_size
        self.fills: list[Fill] = []
        self._clock: datetime | None = None  # stamped onto fills, set per bar

    def set_time(self, ts: datetime) -> None:
        """Set the timestamp stamped onto subsequent fills (the backtest clock)."""
        self._clock = ts

    @property
    def account(self) -> Account:
        return self._account

    def cash(self) -> float:
        return self._account.cash

    def positions(self) -> dict[str, Position]:
        return self._account.positions

    def place_order(self, order: Order) -> Fill | None:
        """Settle ``order`` against the account, or reject it.

        Fills the whole quantity at ``order.price`` and charges costs. Returns the
        resulting :class:`Fill` (also appended to ``fills``), or ``None`` if the
        order is rejected — non-lot quantity, insufficient cash, or overselling.

        BUY adds shares and updates the weighted-average entry price (used by the
        stop-loss and P&L); SELL releases shares and frees the position when it
        reaches zero. Cash moves by ``notional ± cost`` (costs are always paid).
        """
        # Reject anything that isn't a positive whole number of board lots.
        if order.shares <= 0 or order.shares % self._lot != 0:
            return None
        notional = order.shares * order.price
        cost = self._costs.trade_cost(
            notional,
            is_sell=order.side == Side.SELL,
            participation=order.participation,
        )

        if order.side == Side.BUY:
            # Capital constraint: must cover price *and* cost — no margin.
            if notional + cost > self._account.cash:
                return None
            self._account.cash -= notional + cost
            # Open or add to the position, re-deriving the average entry price as a
            # share-weighted blend of the old and new lots.
            pos = self._account.positions.setdefault(
                order.symbol, Position(order.symbol)
            )
            new_shares = pos.shares + order.shares
            pos.avg_price = (pos.avg_price * pos.shares + notional) / new_shares
            pos.shares = new_shares
        else:  # SELL
            # Can only sell shares actually held — no shorting / overselling.
            pos = self._account.positions.get(order.symbol)
            if pos is None or pos.shares < order.shares:
                return None
            self._account.cash += notional - cost  # proceeds net of cost
            pos.shares -= order.shares
            if pos.shares == 0:
                del self._account.positions[order.symbol]  # flat → drop the entry

        # Record the completed trade (drives the report + trade-level analysis).
        fill = Fill(
            symbol=order.symbol,
            side=order.side,
            shares=order.shares,
            price=order.price,
            cost=cost,
            reason=order.reason,
            timestamp=self._clock,
        )
        self.fills.append(fill)
        return fill
