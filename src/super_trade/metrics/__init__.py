"""Technical-indicator metrics for OHLCV bars.

Every metric is a function returning a Polars expression, designed to be applied
to a time-ordered bars DataFrame (as returned by ``DataStore.read_bars``):

    import polars as pl
    from super_trade import metrics as m

    df = store.read_bars("600519", Interval.DAY)
    df = df.with_columns(
        m.sma("close", 20).alias("sma_20"),
        m.rsi("close", 14).alias("rsi_14"),
        m.atr(14).alias("atr_14"),
    )
    # multi-output metrics return a struct -> unnest it:
    df = df.with_columns(m.macd().alias("macd")).unnest("macd")

Metrics are pure functions over whatever bars you pass in; they never touch the
store, so backtests still read real data from a ``DataStore``.

``METRICS`` maps each metric name to its function for programmatic discovery.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

from .momentum import (
    cci,
    momentum,
    roc,
    rsi,
    stochastic_oscillator,
    williams_r,
)
from .returns import (
    cumulative_return,
    drawdown,
    log_return,
    simple_return,
)
from .summary import (
    annualized_volatility,
    cagr,
    calmar_ratio,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
    total_return,
)
from .trend import ema, macd, sma, wma
from .volatility import atr, bollinger_bands, rolling_volatility, true_range
from .volume import obv, typical_price, volume_sma, vwap

# Registry of every metric, keyed by name. Struct-returning (multi-output)
# metrics are marked so callers know to ``.unnest()`` the result.
METRICS: dict[str, Callable[..., pl.Expr]] = {
    # returns (per-bar)
    "simple_return": simple_return,
    "log_return": log_return,
    "cumulative_return": cumulative_return,
    "drawdown": drawdown,
    # trend
    "sma": sma,
    "ema": ema,
    "wma": wma,
    "macd": macd,
    # momentum
    "roc": roc,
    "momentum": momentum,
    "rsi": rsi,
    "stochastic_oscillator": stochastic_oscillator,
    "williams_r": williams_r,
    "cci": cci,
    # volatility
    "true_range": true_range,
    "atr": atr,
    "bollinger_bands": bollinger_bands,
    "rolling_volatility": rolling_volatility,
    # volume
    "typical_price": typical_price,
    "obv": obv,
    "vwap": vwap,
    "volume_sma": volume_sma,
    # summary (scalar aggregates)
    "total_return": total_return,
    "cagr": cagr,
    "annualized_volatility": annualized_volatility,
    "sharpe_ratio": sharpe_ratio,
    "sortino_ratio": sortino_ratio,
    "max_drawdown": max_drawdown,
    "calmar_ratio": calmar_ratio,
}

# Metrics that return a Polars struct (multiple output columns to unnest).
STRUCT_METRICS: frozenset[str] = frozenset(
    {"macd", "bollinger_bands", "stochastic_oscillator"}
)

# Metrics that aggregate the series to a single scalar (use in select/agg, not
# with_columns). The rest produce one value per bar.
SCALAR_METRICS: frozenset[str] = frozenset(
    {
        "total_return",
        "cagr",
        "annualized_volatility",
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown",
        "calmar_ratio",
    }
)

__all__ = [
    "METRICS",
    "SCALAR_METRICS",
    "STRUCT_METRICS",
    "annualized_volatility",
    "atr",
    "bollinger_bands",
    "cagr",
    "calmar_ratio",
    "cci",
    "cumulative_return",
    "drawdown",
    "ema",
    "log_return",
    "macd",
    "max_drawdown",
    "momentum",
    "obv",
    "roc",
    "rolling_volatility",
    "rsi",
    "sharpe_ratio",
    "simple_return",
    "sma",
    "sortino_ratio",
    "stochastic_oscillator",
    "total_return",
    "true_range",
    "typical_price",
    "volume_sma",
    "vwap",
    "williams_r",
    "wma",
]
