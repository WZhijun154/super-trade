"""Return- and drawdown-based metrics.

Each function returns a Polars expression to use inside ``df.with_columns(...)``.
Bars are assumed time-ordered ascending (as returned by ``DataStore.read_bars``).
"""

from __future__ import annotations

import polars as pl


def simple_return(column: str = "close", periods: int = 1) -> pl.Expr:
    """Simple (arithmetic) percentage return over ``periods`` bars."""
    return pl.col(column).pct_change(periods)


def log_return(column: str = "close", periods: int = 1) -> pl.Expr:
    """Natural-log return over ``periods`` bars."""
    return (pl.col(column) / pl.col(column).shift(periods)).log()


def cumulative_return(column: str = "close") -> pl.Expr:
    """Cumulative return relative to the first bar (0 at the start)."""
    return pl.col(column) / pl.col(column).first() - 1


def drawdown(column: str = "close") -> pl.Expr:
    """Fractional drawdown curve from the running peak (always <= 0).

    For the single worst value, see ``summary.max_drawdown``.
    """
    return pl.col(column) / pl.col(column).cum_max() - 1
