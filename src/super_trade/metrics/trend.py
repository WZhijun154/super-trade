"""Trend / moving-average metrics."""

from __future__ import annotations

import polars as pl


def sma(column: str = "close", window: int = 20) -> pl.Expr:
    """Simple moving average over ``window`` bars."""
    return pl.col(column).rolling_mean(window)


def ema(column: str = "close", span: int = 20) -> pl.Expr:
    """Exponential moving average (standard, ``adjust=False``)."""
    return pl.col(column).ewm_mean(span=span, adjust=False)


def wma(column: str = "close", window: int = 20) -> pl.Expr:
    """Linearly-weighted moving average (most recent bar weighted highest)."""
    weights = [float(i) for i in range(1, window + 1)]
    return pl.col(column).rolling_mean(window, weights=weights)


def macd(
    column: str = "close",
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pl.Expr:
    """MACD as a struct of ``{macd, signal, histogram}``.

    Usage: ``df.with_columns(macd().alias("macd")).unnest("macd")``.
    """
    fast_ema = pl.col(column).ewm_mean(span=fast, adjust=False)
    slow_ema = pl.col(column).ewm_mean(span=slow, adjust=False)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm_mean(span=signal, adjust=False)
    histogram = macd_line - signal_line
    return pl.struct(
        macd_line.alias("macd"),
        signal_line.alias("signal"),
        histogram.alias("histogram"),
    )
