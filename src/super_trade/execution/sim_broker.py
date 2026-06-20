"""Simulated broker — fills orders against an in-memory account.

Used for the event-driven backtest and for dry runs. Enforces cash availability,
board-lot sizing, and the same A-share costs as the vectorized backtester
(reusing ``CostModel``). This is the safe default; no real orders are ever sent.
"""

from __future__ import annotations

from super_trade.backtest.costs import CostModel

from .broker import LOT_SIZE, Account, Broker, Fill, Order, Position, Side


class SimBroker(Broker):
    """A broker that simulates fills at the order's reference price."""

    def __init__(
        self,
        cash: float,
        costs: CostModel | None = None,
        lot_size: int = LOT_SIZE,
    ) -> None:
        self._account = Account(cash=cash)
        self._costs = costs or CostModel()
        self._lot = lot_size
        self.fills: list[Fill] = []

    @property
    def account(self) -> Account:
        return self._account

    def cash(self) -> float:
        return self._account.cash

    def positions(self) -> dict[str, Position]:
        return self._account.positions

    def place_order(self, order: Order) -> Fill | None:
        if order.shares <= 0 or order.shares % self._lot != 0:
            return None  # must be a positive whole number of lots
        notional = order.shares * order.price
        cost = self._costs.trade_cost(notional, is_sell=order.side == Side.SELL)

        if order.side == Side.BUY:
            if notional + cost > self._account.cash:
                return None  # insufficient cash (capital constraint)
            self._account.cash -= notional + cost
            pos = self._account.positions.setdefault(
                order.symbol, Position(order.symbol)
            )
            new_shares = pos.shares + order.shares
            pos.avg_price = (pos.avg_price * pos.shares + notional) / new_shares
            pos.shares = new_shares
        else:  # SELL
            pos = self._account.positions.get(order.symbol)
            if pos is None or pos.shares < order.shares:
                return None  # can't sell what you don't hold
            self._account.cash += notional - cost
            pos.shares -= order.shares
            if pos.shares == 0:
                del self._account.positions[order.symbol]

        fill = Fill(
            symbol=order.symbol,
            side=order.side,
            shares=order.shares,
            price=order.price,
            cost=cost,
            reason=order.reason,
        )
        self.fills.append(fill)
        return fill
