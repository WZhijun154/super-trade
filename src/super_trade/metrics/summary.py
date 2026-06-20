"""Scalar summary statistics over a whole series.

Unlike the per-bar indicators, these *aggregate* a series to a single number
(risk/return summary). Each returns an aggregating Polars expression — use it in
``select`` for one value, or ``group_by(...).agg(...)`` for one value per symbol:

    df.select(m.sharpe_ratio().alias("sharpe")).item()
    panel.group_by("symbol").agg(m.sharpe_ratio().alias("sharpe"))

Returns are computed as simple (arithmetic) per-bar returns of ``column``;
``periods_per_year`` is the annualization factor (252 for daily bars).
"""

from __future__ import annotations

import math

import polars as pl


def total_return(column: str = "close") -> pl.Expr:
    """Total return from the first to the last bar."""
    return pl.col(column).last() / pl.col(column).first() - 1


def cagr(column: str = "close", periods_per_year: int = 252) -> pl.Expr:
    """Compound annual growth rate (annualized total return)."""
    growth = pl.col(column).last() / pl.col(column).first()
    n_periods = pl.col(column).count() - 1
    return growth.pow(periods_per_year / n_periods) - 1


def annualized_volatility(
    column: str = "close", periods_per_year: int = 252
) -> pl.Expr:
    """Annualized standard deviation of per-bar returns."""
    returns = pl.col(column).pct_change()
    return returns.std() * math.sqrt(periods_per_year)


def sharpe_ratio(
    column: str = "close",
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
) -> pl.Expr:
    """Annualized Sharpe ratio (excess mean return / volatility)."""
    returns = pl.col(column).pct_change()
    rf = risk_free_rate / periods_per_year
    return (returns.mean() - rf) / returns.std() * math.sqrt(periods_per_year)


def sortino_ratio(
    column: str = "close",
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
) -> pl.Expr:
    """Annualized Sortino ratio (excess return / downside deviation)."""
    returns = pl.col(column).pct_change()
    rf = risk_free_rate / periods_per_year
    downside = pl.when(returns < 0).then(returns).otherwise(0.0)
    downside_dev = downside.pow(2).mean().sqrt()
    return (returns.mean() - rf) / downside_dev * math.sqrt(periods_per_year)


def max_drawdown(column: str = "close") -> pl.Expr:
    """Worst (most negative) peak-to-trough drawdown over the series."""
    return (pl.col(column) / pl.col(column).cum_max() - 1).min()


def calmar_ratio(column: str = "close", periods_per_year: int = 252) -> pl.Expr:
    """CAGR divided by the magnitude of the maximum drawdown."""
    return cagr(column, periods_per_year) / max_drawdown(column).abs()
