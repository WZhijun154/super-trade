"""Unit tests for technical-indicator metrics (pure Polars, no DB)."""

from __future__ import annotations

import math

import polars as pl
import pytest

from super_trade import metrics as m


def _ohlcv(closes: list[float]) -> pl.DataFrame:
    """Build a minimal OHLCV frame from a close series (h/l bracket the close)."""
    return pl.DataFrame(
        {
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1000 + i * 10 for i in range(len(closes))],
        }
    )


def test_sma() -> None:
    df = _ohlcv([1, 2, 3, 4, 5]).with_columns(m.sma("close", 2).alias("sma"))
    got = df["sma"].to_list()
    assert got[0] is None
    assert got[1:] == [1.5, 2.5, 3.5, 4.5]


def test_simple_and_log_return() -> None:
    df = _ohlcv([10, 11, 22]).with_columns(
        m.simple_return("close").alias("r"),
        m.log_return("close").alias("lr"),
    )
    r = df["r"].to_list()
    assert r[0] is None
    assert r[1] == pytest.approx(0.1)
    assert r[2] == pytest.approx(1.0)
    assert df["lr"].to_list()[1] == pytest.approx(math.log(11 / 10))


def test_ema_first_equals_first_value() -> None:
    df = _ohlcv([5, 6, 7]).with_columns(m.ema("close", 3).alias("ema"))
    assert df["ema"].to_list()[0] == pytest.approx(5.0)


def test_rsi_bounds_and_all_gains() -> None:
    df = _ohlcv([float(i) for i in range(1, 30)]).with_columns(
        m.rsi("close", 14).alias("rsi")
    )
    vals = [v for v in df["rsi"].to_list() if v is not None and not math.isnan(v)]
    assert all(0 <= v <= 100 for v in vals)
    # strictly increasing series -> RSI pinned near 100
    assert vals[-1] == pytest.approx(100.0)


def test_drawdown_non_positive_and_max() -> None:
    df = _ohlcv([10, 12, 9, 11]).with_columns(m.drawdown("close").alias("dd"))
    assert all(v <= 1e-9 for v in df["dd"].to_list())
    md = _ohlcv([10, 12, 9, 11]).select(m.max_drawdown("close").alias("md"))
    assert md["md"][0] == pytest.approx(9 / 12 - 1)


def test_true_range_and_atr() -> None:
    df = _ohlcv([10, 11, 12]).with_columns(m.true_range().alias("tr"))
    # first bar: high-low = 2 (no previous close)
    assert df["tr"].to_list()[0] == pytest.approx(2.0)
    df2 = _ohlcv([10, 11, 12]).with_columns(m.atr(2).alias("atr"))
    assert df2["atr"].null_count() == 0


def test_obv_direction() -> None:
    df = _ohlcv([10, 11, 10]).with_columns(m.obv().alias("obv"))
    obv = df["obv"].to_list()
    # up day adds volume, down day subtracts it
    assert obv[1] == pytest.approx(obv[0] + df["volume"][1])
    assert obv[2] == pytest.approx(obv[1] - df["volume"][2])


def test_macd_struct_unnest() -> None:
    df = (
        _ohlcv([float(i) for i in range(1, 40)])
        .with_columns(m.macd().alias("macd"))
        .unnest("macd")
    )
    assert {"macd", "signal", "histogram"} <= set(df.columns)


def test_bollinger_middle_is_sma() -> None:
    closes = [float(i) for i in range(1, 25)]
    df = (
        _ohlcv(closes)
        .with_columns(
            m.bollinger_bands("close", 20).alias("bb"),
            m.sma("close", 20).alias("sma20"),
        )
        .unnest("bb")
    )
    mids = df["middle"].to_list()
    smas = df["sma20"].to_list()
    for a, b in zip(mids, smas, strict=True):
        assert (a is None and b is None) or a == pytest.approx(b)


def test_registry_covers_exports() -> None:
    assert "rsi" in m.METRICS and "macd" in m.METRICS
    assert set(m.METRICS) >= m.STRUCT_METRICS
    # every registered metric is callable
    assert all(callable(fn) for fn in m.METRICS.values())
