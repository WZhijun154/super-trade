"""Unit tests for the Plotly chart builders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import plotly.graph_objects as go
import polars as pl

from super_trade import metrics as m
from super_trade.viz import charts


def _bars(n: int = 40) -> pl.DataFrame:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    ts = [start + timedelta(days=i) for i in range(n)]
    close = [100.0 + i for i in range(n)]
    return pl.DataFrame(
        {
            "timestamp": ts,
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "volume": [1000 + i for i in range(n)],
        }
    )


def test_candlestick_with_overlay() -> None:
    df = _bars().with_columns(m.sma("close", 5).alias("sma_5"))
    fig = charts.candlestick(df, overlays=["sma_5"], title="X")
    assert isinstance(fig, go.Figure)
    types = [t.type for t in fig.data]
    assert "candlestick" in types
    assert any(t.name == "sma_5" for t in fig.data)


def test_price_with_indicators_panels() -> None:
    df = (
        _bars()
        .with_columns(
            m.sma("close", 5).alias("sma_5"), m.rsi("close", 14).alias("rsi_14")
        )
        .with_columns(m.macd().alias("macd"))
        .unnest("macd")
    )
    fig = charts.price_with_indicators(
        df, overlays=["sma_5"], volume=True, subplots=[["rsi_14"], ["macd", "signal"]]
    )
    assert isinstance(fig, go.Figure)
    # candlestick + sma overlay + volume bar + rsi + macd + signal = 6 traces
    assert len(fig.data) == 6
    assert any(t.type == "bar" for t in fig.data)  # volume panel


def test_equity_and_drawdown() -> None:
    df = _bars()
    eq = charts.equity_curve(df)
    dd = charts.drawdown_chart(df)
    assert isinstance(eq, go.Figure) and isinstance(dd, go.Figure)
    assert dd.data[0].fill == "tozeroy"


def test_line_chart() -> None:
    df = _bars().with_columns(m.ema("close", 10).alias("ema_10"))
    fig = charts.line_chart(df, ["close", "ema_10"])
    assert {t.name for t in fig.data} == {"close", "ema_10"}
