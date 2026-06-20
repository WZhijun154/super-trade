"""Strategy interface for vectorized backtests.

A strategy maps bars (via the ``metrics`` indicators) to a **target weight** per
bar, expressed as a Polars expression — 1.0 = fully long, 0 = flat, negative =
short. Returning an expression keeps strategies composable with ``metrics`` and
lets them extend to multi-symbol panels later via ``.over("symbol")``.

The engine, not the strategy, enforces no-lookahead (it lags the target by one
bar), so a strategy is free to use the current bar's close in its signal.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import polars as pl


class Strategy(ABC):
    """A target-weight strategy for the vectorized engine."""

    name: str = "strategy"

    @abstractmethod
    def positions(self) -> pl.Expr:
        """Return the target weight per bar as a Polars expression."""
