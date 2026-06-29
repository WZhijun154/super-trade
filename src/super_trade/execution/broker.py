"""Broker abstraction — the bridge between backtest and live trading.

The same strategy + risk logic runs against any ``Broker``:

* ``SimBroker`` fills orders against a simulated ``Account`` (backtest / dry runs).
* ``QmtBroker`` sends real orders via QMT's ``xttrade`` (live, simulation account).

Code that places orders depends only on this interface, so switching from a
simulated run to a live QMT-simulation account is a one-line change of broker.
Quantities are in **shares** (A-share lots of 100); cash and prices in ¥.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

LOT_SIZE = 100  # A-share board lot (1 手 = 100 shares)


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Order:
    """An instruction to buy/sell ``shares`` of ``symbol`` near ``price``."""

    symbol: str
    side: Side
    shares: int
    price: float  # reference/limit price (current quote)
    reason: str = ""
    # Order shares ÷ the bar's volume — lets the SimBroker charge size-dependent
    # market impact. 0 (default, e.g. live orders) = no modelled impact.
    participation: float = 0.0


@dataclass(frozen=True)
class Fill:
    """A completed trade, including the cost charged."""

    symbol: str
    side: Side
    shares: int
    price: float
    cost: float
    reason: str = ""
    timestamp: datetime | None = None


@dataclass
class Position:
    """A holding, with the average entry price (used for stops and P&L)."""

    symbol: str
    shares: int = 0
    avg_price: float = 0.0


@dataclass
class Account:
    """Cash plus open positions; the unit of P&L accounting."""

    cash: float
    positions: dict[str, Position] = field(default_factory=dict)

    def shares(self, symbol: str) -> int:
        pos = self.positions.get(symbol)
        return pos.shares if pos else 0

    def market_value(self, prices: dict[str, float]) -> float:
        return sum(
            pos.shares * prices.get(sym, pos.avg_price)
            for sym, pos in self.positions.items()
        )

    def equity(self, prices: dict[str, float]) -> float:
        """Total account value: cash + marked-to-market positions."""
        return self.cash + self.market_value(prices)


class Broker(ABC):
    """Places orders and reports cash/positions. Sim or live."""

    @abstractmethod
    def cash(self) -> float: ...

    @abstractmethod
    def positions(self) -> dict[str, Position]: ...

    @abstractmethod
    def place_order(self, order: Order) -> Fill | None:
        """Submit an order. Returns the ``Fill`` or ``None`` if rejected."""

    def shares(self, symbol: str) -> int:
        pos = self.positions().get(symbol)
        return pos.shares if pos else 0
