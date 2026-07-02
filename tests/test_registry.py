"""Tests for the STRATEGIES registry + build_strategy factory."""

from __future__ import annotations

import pytest

from super_trade.backtest import STRATEGIES, SmaCross, build_strategy
from super_trade.backtest.strategy import Strategy


def test_build_strategy_with_params() -> None:
    strat = build_strategy("sma_cross", {"fast": 5, "slow": 20})
    assert isinstance(strat, SmaCross)
    assert (strat.fast, strat.slow) == (5, 20)
    assert strat.name == "sma_cross_5_20"  # instance name bakes in the params


def test_build_strategy_defaults() -> None:
    strat = build_strategy("buy_and_hold")
    assert strat.name == "buy_and_hold"


def test_unknown_strategy_raises() -> None:
    with pytest.raises(KeyError, match="unknown strategy"):
        build_strategy("does_not_exist")


def test_registry_values_are_strategies() -> None:
    for name, cls in STRATEGIES.items():
        assert issubclass(cls, Strategy), name
