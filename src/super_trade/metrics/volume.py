"""Volume-based metrics."""

from __future__ import annotations

import polars as pl


def typical_price(
    high: str = "high", low: str = "low", close: str = "close"
) -> pl.Expr:
    """Typical price: mean of high, low, and close."""
    return (pl.col(high) + pl.col(low) + pl.col(close)) / 3


def obv(close: str = "close", volume: str = "volume") -> pl.Expr:
    """On-Balance Volume: running sum of volume signed by price direction."""
    direction = pl.col(close).diff().sign().fill_null(0.0)
    return (direction * pl.col(volume)).cum_sum()


def vwap(
    high: str = "high",
    low: str = "low",
    close: str = "close",
    volume: str = "volume",
) -> pl.Expr:
    """Cumulative volume-weighted average price over the series."""
    tp = (pl.col(high) + pl.col(low) + pl.col(close)) / 3
    return (tp * pl.col(volume)).cum_sum() / pl.col(volume).cum_sum()


def volume_sma(window: int = 20, volume: str = "volume") -> pl.Expr:
    """Simple moving average of volume over ``window`` bars."""
    return pl.col(volume).rolling_mean(window)
