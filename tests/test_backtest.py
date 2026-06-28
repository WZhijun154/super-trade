"""Unit tests for the vectorized backtest engine (synthetic bars)."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from super_trade.backtest import (
    NO_COSTS,
    BuyAndHold,
    CostModel,
    SmaCross,
    Strategy,
    VectorizedEngine,
)


def _bars(closes: list[float]) -> pl.DataFrame:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    ts = [start + timedelta(days=i) for i in range(len(closes))]
    return pl.DataFrame({"timestamp": ts, "close": closes})


class _AlwaysLong(Strategy):
    name = "always_long"

    def positions(self) -> pl.Expr:
        return pl.lit(1.0)


def test_buy_and_hold_zero_cost_matches_price() -> None:
    closes = [100.0, 110.0, 99.0, 121.0]
    res = VectorizedEngine(NO_COSTS).run(_bars(closes), BuyAndHold())
    equity = res.data["equity"].to_list()
    # held lags one bar but the first held bar captures the close[0]->close[1]
    # move, so total equity equals close[-1] / close[0].
    assert equity[0] == pytest.approx(1.0)
    assert equity[-1] == pytest.approx(closes[-1] / closes[0])


def test_no_lookahead_position_is_lagged() -> None:
    res = VectorizedEngine(NO_COSTS).run(_bars([10, 11, 12, 13]), _AlwaysLong())
    held = res.data["held"].to_list()
    assert held[0] == 0.0  # not yet invested on the first bar
    assert held[1:] == [1.0, 1.0, 1.0]


def test_costs_reduce_return() -> None:
    closes = [100.0, 101.0, 100.0, 102.0, 101.0, 103.0]
    free = VectorizedEngine(NO_COSTS).run(_bars(closes), SmaCross(2, 3))
    costed = VectorizedEngine(CostModel()).run(_bars(closes), SmaCross(2, 3))
    assert costed.data["equity"][-1] <= free.data["equity"][-1]


def test_stamp_tax_only_on_sell() -> None:
    # one entry (buy) then one exit (sell)
    bars = _bars([100.0, 100.0, 100.0, 100.0])
    # zero every rate except stamp tax to isolate the sell-only charge
    model = CostModel(
        commission_rate=0.0,
        stamp_tax_rate=0.001,
        transfer_fee_rate=0.0,
        slippage_rate=0.0,
    )

    class _InThenOut(Strategy):
        name = "in_then_out"

        def positions(self) -> pl.Expr:
            # target long on bars 0-1 then flat -> held buys at bar 1, sells at bar 3
            return pl.when(pl.int_range(pl.len()) < 2).then(1.0).otherwise(0.0)

    res = VectorizedEngine(model).run(bars, _InThenOut())
    costs = res.data["cost"].to_list()
    # buy incurs no stamp tax; only the sell (held 1 -> 0) does
    assert sum(costs) == pytest.approx(0.001)


def test_smacross_stats_well_formed() -> None:
    closes = [100.0 + math.sin(i / 3) * 5 + i * 0.1 for i in range(60)]
    res = VectorizedEngine().run(_bars(closes), SmaCross(5, 20))
    stats = res.stats()
    assert {
        "total_return",
        "cagr",
        "annual_vol",
        "sharpe",
        "max_drawdown",
        "calmar",
    } == set(stats)
    assert all(math.isfinite(v) for v in stats.values())
    assert stats["max_drawdown"] <= 1e-9
    assert res.data["equity"][0] == pytest.approx(1.0)
