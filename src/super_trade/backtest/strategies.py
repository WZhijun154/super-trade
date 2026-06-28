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


class ScaledRsiReversion(Strategy):
    """Mean-reversion that *scales* exposure by how oversold RSI is.

    Unlike :class:`RsiReversion` (all-in or all-out), this emits a **fractional
    target weight** that grows as RSI falls and shrinks as it recovers — a linear
    ramp from 0 at ``high`` to 1.0 at ``low``, clamped outside that band:

        RSI >= high → 0.0  (flat)
        RSI <= low  → 1.0  (full)
        in between  → linearly scaled

    The event-driven engine rebalances toward this weight each bar, so as RSI
    drifts the position is **bought and sold in tranches** (scale in while it keeps
    falling, trim as it recovers) — i.e. the same name is traded many times, the
    common real-world pattern. The vectorized engine reads the weight directly as
    the invested fraction.
    """

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
        self.name = f"scaled_rsi_{window}"

    def positions(self) -> pl.Expr:
        rsi = m.rsi(self.column, self.window)
        # Linearly map RSI from `high`→0.0 down to `low`→1.0, then clip to [0, 1].
        weight = (self.high - rsi) / (self.high - self.low)
        # null/NaN during the RSI warm-up → flat (0.0).
        return weight.clip(0.0, 1.0).fill_nan(0.0).fill_null(0.0)
