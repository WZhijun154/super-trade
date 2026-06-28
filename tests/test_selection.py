"""Tests for the stock-selection layer (features, filters, scorers, selector)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl
from fakes import FakeStore

from super_trade.data import Bar, Interval
from super_trade.selection import (
    OHLCV_FEATURES,
    AtLeast,
    AtMost,
    Flag,
    Range,
    Rank,
    Selector,
    build_features,
)


def _cross_section() -> pl.DataFrame:
    """A crafted 4-name feature frame with clear winners/losers per criterion."""
    return pl.DataFrame(
        {
            "symbol": ["A", "B", "C", "D"],
            "float_mktcap": [2e9, 4e9, 50e9, 1e9],  # C huge; D tiny
            "adv": [1e7, 2e7, 5e8, 5e5],  # C too liquid; D too illiquid
            "inst_ownership": [0.05, 0.10, 0.50, 0.08],  # C heavily institutional
            "is_st": [False, False, False, True],  # D is ST
            "momentum": [0.20, -0.10, 0.30, 0.00],
            "volatility": [0.30, 0.40, 0.20, 0.50],
        }
    )


def test_build_features_shape_and_values() -> None:
    store = FakeStore()
    start = datetime(2024, 1, 1, tzinfo=UTC)
    # A steadily rising series → positive momentum, last close 129.
    store.write_bars(
        [
            Bar(
                symbol="AAA",
                interval=Interval.DAY,
                timestamp=start + timedelta(days=i),
                open=100.0 + i,
                high=100.0 + i,
                low=100.0 + i,
                close=100.0 + i,
                volume=1000,
            )
            for i in range(30)
        ]
    )
    feats = build_features(store, ["AAA"], lookback=30)
    assert feats.height == 1
    assert set(OHLCV_FEATURES) <= set(feats.columns)
    row = feats.row(0, named=True)
    assert row["symbol"] == "AAA"
    assert row["price"] == 129.0
    assert row["momentum"] > 0  # rising series
    assert row["adv"] > 0


def test_retail_pond_filter_composes() -> None:
    df = _cross_section()
    pond = (
        Range("float_mktcap", high=10e9)  # small float cap
        & Range("adv", low=5e6, high=1e8)  # tradeable, not quant-sized
        & AtMost("inst_ownership", 0.20)  # low institutional ownership
        & ~Flag("is_st")  # drop ST
    )
    keep = df.filter(pond.mask().fill_null(False))["symbol"].to_list()
    # C fails (too big/liquid/institutional); D fails (illiquid + ST) → A, B remain.
    assert keep == ["A", "B"]


def test_filter_or_and_not() -> None:
    df = _cross_section()
    either = Flag("is_st") | AtLeast("momentum", 0.25)  # D (ST) or C (mom .3)
    assert set(df.filter(either.mask().fill_null(False))["symbol"]) == {"C", "D"}
    not_st = ~Flag("is_st")
    assert "D" not in df.filter(not_st.mask().fill_null(False))["symbol"].to_list()


def test_scorer_blend_ranks() -> None:
    df = _cross_section()
    # prefer low institutional ownership AND high momentum
    score = Rank("inst_ownership", ascending=True) + Rank("momentum", ascending=False)
    ranked = df.with_columns(score.score().alias("s"))
    s = dict(zip(ranked["symbol"], ranked["s"], strict=True))
    # A dominates B on both axes (lower inst, higher momentum) → strictly higher score
    assert s["A"] > s["B"]


def test_selector_filter_score_top_n() -> None:
    df = _cross_section()
    sel = Selector(
        filters=[Range("float_mktcap", high=10e9), ~Flag("is_st")],
        score=Rank("momentum", ascending=False),
        top_n=1,
    )
    # A, B, D pass mktcap; D is ST → out. Of A/B, A has higher momentum → top pick.
    assert sel.select(df) == ["A"]


def test_selector_empty_cross_section() -> None:
    empty = pl.DataFrame(schema={"symbol": pl.String, "momentum": pl.Float64})
    assert Selector(score=Rank("momentum"), top_n=5).select(empty) == []
