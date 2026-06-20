"""Pure Plotly chart builders for OHLCV bars.

Each function takes a time-ordered Polars DataFrame (as returned by
``DataStore.read_bars``, optionally with metric columns already added) and returns
a ``plotly.graph_objects.Figure``. They never query the store or compute metrics
themselves — the caller composes store -> metrics -> charts — which keeps them
usable from notebooks, scripts, and the Streamlit app alike.
"""

from __future__ import annotations

from collections.abc import Sequence

import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots


def candlestick(
    df: pl.DataFrame,
    *,
    overlays: Sequence[str] = (),
    title: str = "",
    x: str = "timestamp",
) -> go.Figure:
    """Single-panel candlestick with optional line overlays (e.g. moving averages).

    ``overlays`` are column names already present on ``df`` (typically metric
    outputs) drawn as lines on the price axis.
    """
    xs = df[x].to_list()
    fig = go.Figure(
        go.Candlestick(
            x=xs,
            open=df["open"].to_list(),
            high=df["high"].to_list(),
            low=df["low"].to_list(),
            close=df["close"].to_list(),
            name="price",
        )
    )
    for col in overlays:
        fig.add_scatter(x=xs, y=df[col].to_list(), mode="lines", name=col)
    fig.update_layout(title=title, xaxis_rangeslider_visible=False)
    return fig


def price_with_indicators(
    df: pl.DataFrame,
    *,
    overlays: Sequence[str] = (),
    volume: bool = True,
    subplots: Sequence[Sequence[str]] = (),
    title: str = "",
    x: str = "timestamp",
) -> go.Figure:
    """Multi-panel chart: candlestick (+overlays) on top, then volume and/or
    one stacked panel per entry in ``subplots`` (each a list of columns to plot).

    Example::

        price_with_indicators(df, overlays=["sma_20"], volume=True,
                              subplots=[["rsi_14"], ["macd", "signal"]])
    """
    n_extra = (1 if volume else 0) + len(subplots)
    rows = 1 + n_extra
    if n_extra:
        price_h = 0.5
        row_heights = [price_h, *([(1 - price_h) / n_extra] * n_extra)]
    else:
        row_heights = [1.0]

    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
    )
    xs = df[x].to_list()
    fig.add_trace(
        go.Candlestick(
            x=xs,
            open=df["open"].to_list(),
            high=df["high"].to_list(),
            low=df["low"].to_list(),
            close=df["close"].to_list(),
            name="price",
        ),
        row=1,
        col=1,
    )
    for col in overlays:
        fig.add_trace(
            go.Scatter(x=xs, y=df[col].to_list(), mode="lines", name=col),
            row=1,
            col=1,
        )

    row = 2
    if volume:
        fig.add_trace(
            go.Bar(x=xs, y=df["volume"].to_list(), name="volume"), row=row, col=1
        )
        row += 1
    for panel in subplots:
        for col in panel:
            fig.add_trace(
                go.Scatter(x=xs, y=df[col].to_list(), mode="lines", name=col),
                row=row,
                col=1,
            )
        row += 1

    fig.update_layout(title=title, xaxis_rangeslider_visible=False)
    return fig


def line_chart(
    df: pl.DataFrame,
    columns: Sequence[str],
    *,
    x: str = "timestamp",
    title: str = "",
) -> go.Figure:
    """Plot one or more columns as lines against ``x``."""
    xs = df[x].to_list()
    fig = go.Figure()
    for col in columns:
        fig.add_scatter(x=xs, y=df[col].to_list(), mode="lines", name=col)
    fig.update_layout(title=title)
    return fig


def equity_curve(
    df: pl.DataFrame,
    *,
    column: str = "close",
    x: str = "timestamp",
    title: str = "Equity curve",
) -> go.Figure:
    """Cumulative-return curve from a price column."""
    from super_trade import metrics as m

    eq = df.select(pl.col(x), m.cumulative_return(column).alias("cumret"))
    fig = go.Figure(
        go.Scatter(
            x=eq[x].to_list(),
            y=eq["cumret"].to_list(),
            mode="lines",
            name="cumulative return",
        )
    )
    fig.update_layout(title=title, yaxis_tickformat=".0%")
    return fig


def drawdown_chart(
    df: pl.DataFrame,
    *,
    column: str = "close",
    x: str = "timestamp",
    title: str = "Drawdown",
) -> go.Figure:
    """Drawdown-from-peak area chart from a price column."""
    from super_trade import metrics as m

    dd = df.select(pl.col(x), m.drawdown(column).alias("dd"))
    fig = go.Figure(
        go.Scatter(
            x=dd[x].to_list(),
            y=dd["dd"].to_list(),
            mode="lines",
            fill="tozeroy",
            name="drawdown",
        )
    )
    fig.update_layout(title=title, yaxis_tickformat=".0%")
    return fig
