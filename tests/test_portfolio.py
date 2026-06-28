"""Tests for the portfolio-allocation layer (EqualWeight, InverseVol, …)."""

from __future__ import annotations

import polars as pl

from super_trade.portfolio import EqualWeight, InverseVol, ScoreProportional


def _feats() -> pl.DataFrame:
    # A is the quiet name (low vol) and the high-score name.
    return pl.DataFrame(
        {
            "symbol": ["A", "B", "C"],
            "volatility": [0.20, 0.40, 0.40],
            "score": [3.0, 1.0, 1.0],
        }
    )


def test_equal_weight_sums_to_gross() -> None:
    w = EqualWeight(gross=0.9, max_weight=0.5).weights(_feats())
    assert len(w) == 3
    assert all(abs(v - 0.3) < 1e-9 for v in w.values())  # 0.9 / 3
    assert abs(sum(w.values()) - 0.9) < 1e-9


def test_equal_weight_cap_binds() -> None:
    # 3 names capped at 0.2 → 0.6 total, below gross: caps bind, no scale-up.
    w = EqualWeight(gross=0.9, max_weight=0.2).weights(_feats())
    assert all(abs(v - 0.2) < 1e-9 for v in w.values())
    assert abs(sum(w.values()) - 0.6) < 1e-9


def test_inverse_vol_prefers_low_vol() -> None:
    w = InverseVol(gross=0.99, max_weight=0.9).weights(_feats())
    assert w["A"] > w["B"]  # lower vol → more capital
    assert abs(w["B"] - w["C"]) < 1e-9  # equal vol → equal weight
    assert abs(sum(w.values()) - 0.99) < 1e-9  # no cap binding → gross fully used


def test_inverse_vol_respects_max_weight() -> None:
    w = InverseVol(gross=0.99, max_weight=0.4).weights(_feats())
    assert all(v <= 0.4 + 1e-9 for v in w.values())


def test_score_proportional() -> None:
    w = ScoreProportional("score", gross=0.9, max_weight=0.9).weights(_feats())
    # scores 3:1:1 → A gets 3x the others
    assert abs(w["A"] - 3 * w["B"]) < 1e-9
    assert abs(sum(w.values()) - 0.9) < 1e-9


def test_empty_features_give_no_weights() -> None:
    empty = pl.DataFrame(schema={"symbol": pl.String, "volatility": pl.Float64})
    assert InverseVol().weights(empty) == {}
