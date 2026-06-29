"""Backtest result: the per-bar frame plus performance stats and charts.

Performance stats reuse ``metrics.summary`` on the ``equity`` column (which starts
at 1.0, so its per-bar pct-change equals the strategy return). Charts reuse
``viz`` — equity and drawdown plots come for free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import polars as pl

from super_trade import metrics as m

if TYPE_CHECKING:
    import plotly.graph_objects as go


@dataclass
class BacktestResult:
    """Output of a backtest run.

    ``data`` is the per-bar equity frame (always present). The event-driven engine
    additionally fills ``fills`` (one row per executed trade) and ``positions`` (a
    per-bar snapshot of open holdings) — the telemetry the Foxglove MCAP exporter
    streams. The vectorized engine leaves both ``None``.
    """

    data: pl.DataFrame
    strategy_name: str = "strategy"
    fills: pl.DataFrame | None = None
    positions: pl.DataFrame | None = None
    bars: pl.DataFrame | None = None

    def stats(self) -> dict[str, float]:
        """Risk/return summary, computed on the equity curve."""
        row = self.data.select(
            m.total_return("equity").alias("total_return"),
            m.cagr("equity").alias("cagr"),
            m.annualized_volatility("equity").alias("annual_vol"),
            m.sharpe_ratio("equity").alias("sharpe"),
            m.max_drawdown("equity").alias("max_drawdown"),
            m.calmar_ratio("equity").alias("calmar"),
        ).row(0, named=True)
        return dict(row)

    def trades(self) -> pl.DataFrame:
        """Bars where the held position changed (entries/exits/rebalances)."""
        change = pl.col("held") - pl.col("held").shift(1).fill_null(0.0)
        return (
            self.data.with_columns(change.alias("delta"))
            .filter(pl.col("delta") != 0)
            .select("timestamp", "close", "held", "delta")
        )

    def equity_curve(self) -> go.Figure:
        """Plotly equity (cumulative-return) curve."""
        from super_trade import viz

        return viz.equity_curve(
            self.data, column="equity", title=f"{self.strategy_name} — equity"
        )

    def drawdown(self) -> go.Figure:
        """Plotly drawdown chart of the equity curve."""
        from super_trade import viz

        return viz.drawdown_chart(
            self.data, column="equity", title=f"{self.strategy_name} — drawdown"
        )
