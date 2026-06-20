"""Momentum / oscillator metrics."""

from __future__ import annotations

import polars as pl


def roc(column: str = "close", periods: int = 10) -> pl.Expr:
    """Rate of change (percent) over ``periods`` bars."""
    return pl.col(column).pct_change(periods) * 100


def momentum(column: str = "close", periods: int = 10) -> pl.Expr:
    """Absolute price momentum: current minus ``periods``-ago value."""
    return pl.col(column) - pl.col(column).shift(periods)


def rsi(column: str = "close", window: int = 14) -> pl.Expr:
    """Relative Strength Index (Wilder's smoothing), bounded 0-100."""
    delta = pl.col(column).diff()
    gain = pl.when(delta > 0).then(delta).otherwise(0.0)
    loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
    avg_gain = gain.ewm_mean(alpha=1 / window, adjust=False)
    avg_loss = loss.ewm_mean(alpha=1 / window, adjust=False)
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def stochastic_oscillator(
    window: int = 14,
    smooth: int = 3,
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> pl.Expr:
    """Stochastic oscillator as a struct of ``{percent_k, percent_d}``."""
    lowest = pl.col(low).rolling_min(window)
    highest = pl.col(high).rolling_max(window)
    percent_k = 100 * (pl.col(close) - lowest) / (highest - lowest)
    percent_d = percent_k.rolling_mean(smooth)
    return pl.struct(percent_k.alias("percent_k"), percent_d.alias("percent_d"))


def williams_r(
    window: int = 14,
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> pl.Expr:
    """Williams %R over ``window`` bars (bounded -100 to 0)."""
    highest = pl.col(high).rolling_max(window)
    lowest = pl.col(low).rolling_min(window)
    return -100 * (highest - pl.col(close)) / (highest - lowest)


def cci(
    window: int = 20,
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> pl.Expr:
    """Commodity Channel Index (uses mean-absolute-deviation approximation)."""
    tp = (pl.col(high) + pl.col(low) + pl.col(close)) / 3
    sma_tp = tp.rolling_mean(window)
    mean_dev = (tp - sma_tp).abs().rolling_mean(window)
    return (tp - sma_tp) / (0.015 * mean_dev)
