"""Execution layer — run strategies live (or dry-run) through a broker.

Shares the :class:`~super_trade.backtest.strategy.Strategy` interface with the
backtester: the same strategy drives a ``SimBroker`` (dry-run / event-driven
backtest) or a ``QmtBroker`` (live, on a QMT simulation account). The
:class:`ExecutionEngine` scans the universe, applies the :class:`RiskManager`
(sizing, stop-loss, daily-loss halt, kill switch), and submits orders.

Safety: ``ExecutionEngine`` defaults to ``dry_run=True`` — it logs the orders it
would send but does not place them. Use a QMT **simulation** account when going
beyond dry-run.
"""

from __future__ import annotations

from .broker import LOT_SIZE, Account, Broker, Fill, Order, Position, Side
from .engine import ExecutionEngine
from .qmt_broker import QmtBroker
from .report import daily_report
from .risk import RiskLimits, RiskManager
from .sim_broker import SimBroker

__all__ = [
    "LOT_SIZE",
    "Account",
    "Broker",
    "ExecutionEngine",
    "Fill",
    "Order",
    "Position",
    "QmtBroker",
    "RiskLimits",
    "RiskManager",
    "Side",
    "SimBroker",
    "daily_report",
]
