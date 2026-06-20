"""Vectorized backtest engine.

Applies a strategy's target weights to asset returns over a whole bars frame at
once. No-lookahead is enforced here: the held position is the target lagged by
one bar, so a signal computed on bar *t*'s close is only traded into on *t+1*.
"""

from __future__ import annotations

import polars as pl

from super_trade import metrics as m

from .costs import NO_COSTS, CostModel
from .result import BacktestResult
from .strategy import Strategy


class VectorizedEngine:
    """Run target-weight strategies against a single symbol's bars."""

    def __init__(self, costs: CostModel | None = None) -> None:
        self._costs = costs if costs is not None else CostModel()

    def run(self, bars: pl.DataFrame, strategy: Strategy) -> BacktestResult:
        """Backtest ``strategy`` on ``bars`` (must have ``timestamp`` + ``close``)."""
        df = bars.sort("timestamp").with_columns(
            strategy.positions().alias("target"),
            m.simple_return("close").alias("asset_ret"),
        )
        # held = what we actually hold during the bar = target decided last bar.
        df = df.with_columns(pl.col("target").shift(1).fill_null(0.0).alias("held"))
        df = df.with_columns(self._costs.cost_expr("held").alias("cost"))
        df = df.with_columns(
            (
                pl.col("held") * pl.col("asset_ret").fill_null(0.0) - pl.col("cost")
            ).alias("ret")
        )
        df = df.with_columns((1 + pl.col("ret")).cum_prod().alias("equity"))
        return BacktestResult(df, strategy_name=strategy.name)


def run_backtest(
    bars: pl.DataFrame, strategy: Strategy, costs: CostModel | None = None
) -> BacktestResult:
    """Convenience one-shot: ``run_backtest(bars, SmaCross())``."""
    return VectorizedEngine(costs).run(bars, strategy)


__all__ = ["NO_COSTS", "VectorizedEngine", "run_backtest"]
