"""Plotly visualization layer.

Pure ``DataFrame -> Figure`` builders that consume bars (+ optional metric
columns) and never touch storage. See :mod:`super_trade.viz.charts`.
"""

from .charts import (
    candlestick,
    drawdown_chart,
    equity_curve,
    line_chart,
    price_with_indicators,
)

__all__ = [
    "candlestick",
    "drawdown_chart",
    "equity_curve",
    "line_chart",
    "price_with_indicators",
]
