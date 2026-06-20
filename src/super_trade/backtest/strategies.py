"""Example strategies, built from ``super_trade.metrics``.

Each returns a target-weight expression; see :class:`Strategy`.
"""

from __future__ import annotations

import polars as pl

from super_trade import metrics as m

from .strategy import Strategy


class BuyAndHold(Strategy):
    """Always fully invested — the benchmark."""

    name = "buy_and_hold"

    def positions(self) -> pl.Expr:
        return pl.lit(1.0)


class SmaCross(Strategy):
    """Long while the fast SMA is above the slow SMA, else flat."""

    def __init__(self, fast: int = 10, slow: int = 30, column: str = "close") -> None:
        self.fast = fast
        self.slow = slow
        self.column = column
        self.name = f"sma_cross_{fast}_{slow}"

    def positions(self) -> pl.Expr:
        fast = m.sma(self.column, self.fast)
        slow = m.sma(self.column, self.slow)
        return pl.when(fast > slow).then(1.0).otherwise(0.0)


class RsiReversion(Strategy):
    """Buy when RSI is oversold, exit when overbought, hold in between."""

    def __init__(
        self,
        window: int = 14,
        low: float = 30.0,
        high: float = 70.0,
        column: str = "close",
    ) -> None:
        self.window = window
        self.low = low
        self.high = high
        self.column = column
        self.name = f"rsi_reversion_{window}"

    def positions(self) -> pl.Expr:
        rsi = m.rsi(self.column, self.window)
        raw = (
            pl.when(rsi < self.low)
            .then(1.0)
            .when(rsi > self.high)
            .then(0.0)
            .otherwise(None)
        )
        return raw.forward_fill().fill_null(0.0)
