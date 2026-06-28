"""Vectorized backtesting.

Reads real bars from a ``DataStore``, turns a :class:`Strategy`'s target weights
into an equity curve (no-lookahead, with transaction costs), and reports stats
and charts by reusing ``metrics`` and ``viz``::

    from super_trade.data import ClickHouseStore, ClickHouseConfig, Interval
    from super_trade.backtest import VectorizedEngine, SmaCross

    bars = store.read_bars("600519", Interval.DAY)
    result = VectorizedEngine().run(bars, SmaCross(10, 30))
    print(result.stats())
    result.equity_curve().show()
"""

from __future__ import annotations

from .costs import NO_COSTS, CostModel
from .engine import VectorizedEngine, run_backtest
from .result import BacktestResult
from .strategies import BuyAndHold, RsiReversion, ScaledRsiReversion, SmaCross
from .strategy import Strategy

__all__ = [
    "NO_COSTS",
    "BacktestResult",
    "BuyAndHold",
    "CostModel",
    "RsiReversion",
    "ScaledRsiReversion",
    "SmaCross",
    "Strategy",
    "VectorizedEngine",
    "run_backtest",
]
