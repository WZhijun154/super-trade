"""Unit tests for scalar summary metrics (pure Polars, no DB)."""

from __future__ import annotations

import math

import polars as pl
import pytest

from super_trade import metrics as m


def _prices(closes: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"close": closes})


def test_total_return() -> None:
    v = _prices([100, 110, 99, 121]).select(m.total_return().alias("x")).item()
    assert v == pytest.approx(0.21)


def test_max_drawdown() -> None:
    v = _prices([100, 110, 99, 121]).select(m.max_drawdown().alias("x")).item()
    assert v == pytest.approx(99 / 110 - 1)  # -0.10


def test_vol_positive_and_sharpe_sign() -> None:
    up = _prices([100, 101, 102, 103, 104, 105])
    assert up.select(m.annualized_volatility().alias("v")).item() > 0
    assert up.select(m.sharpe_ratio().alias("s")).item() > 0
    down = _prices([105, 104, 103, 102, 101, 100])
    assert down.select(m.sharpe_ratio().alias("s")).item() < 0


def test_sortino_cagr_calmar_finite() -> None:
    df = _prices([100, 110, 99, 121, 130, 128])
    for metric in (m.sortino_ratio(), m.cagr(), m.calmar_ratio()):
        assert math.isfinite(df.select(metric.alias("x")).item())


def test_scalar_metric_per_symbol_via_group_by() -> None:
    panel = pl.DataFrame(
        {
            "symbol": ["A", "A", "A", "B", "B", "B"],
            "close": [100.0, 110.0, 121.0, 50.0, 45.0, 40.0],
        }
    )
    out = panel.group_by("symbol").agg(m.total_return().alias("tr")).sort("symbol")
    trs = dict(zip(out["symbol"].to_list(), out["tr"].to_list(), strict=True))
    assert trs["A"] == pytest.approx(0.21)
    assert trs["B"] == pytest.approx(40 / 50 - 1)


def test_registry_marks_scalars() -> None:
    assert set(m.METRICS) >= m.SCALAR_METRICS
    assert "sharpe_ratio" in m.SCALAR_METRICS
    # per-bar metrics are not marked scalar
    assert "sma" not in m.SCALAR_METRICS
