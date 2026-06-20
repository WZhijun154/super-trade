"""Volatility / range-based metrics."""

from __future__ import annotations

import polars as pl


def true_range(high: str = "high", low: str = "low", close: str = "close") -> pl.Expr:
    """True Range: max of high-low and the gaps to the previous close."""
    prev_close = pl.col(close).shift(1)
    return pl.max_horizontal(
        pl.col(high) - pl.col(low),
        (pl.col(high) - prev_close).abs(),
        (pl.col(low) - prev_close).abs(),
    )


def atr(
    window: int = 14,
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> pl.Expr:
    """Average True Range (Wilder's smoothing of True Range)."""
    return true_range(high, low, close).ewm_mean(alpha=1 / window, adjust=False)


def bollinger_bands(
    column: str = "close", window: int = 20, num_std: float = 2.0
) -> pl.Expr:
    """Bollinger Bands as a struct of ``{middle, upper, lower}``."""
    middle = pl.col(column).rolling_mean(window)
    std = pl.col(column).rolling_std(window)
    return pl.struct(
        middle.alias("middle"),
        (middle + num_std * std).alias("upper"),
        (middle - num_std * std).alias("lower"),
    )


def rolling_volatility(
    column: str = "close", window: int = 20, periods: int = 1
) -> pl.Expr:
    """Rolling standard deviation of log returns (per-bar, not annualized)."""
    returns = (pl.col(column) / pl.col(column).shift(periods)).log()
    return returns.rolling_std(window)
