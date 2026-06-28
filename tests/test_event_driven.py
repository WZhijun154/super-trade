"""Tests for the event-driven backtest (replay through SimBroker)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl
from factories import make_bars
from fakes import FakeStore

from super_trade.backtest import BuyAndHold, SmaCross
from super_trade.backtest.strategy import Strategy
from super_trade.data import Bar, Interval
from super_trade.execution import EventDrivenBacktest, RiskLimits, RiskManager

# Near-all-in caps so a target weight isn't clipped by the default 20% per-name
# limit, and the daily-loss halt never fires.
_WIDE = RiskLimits(
    max_position_weight=0.95, max_gross_exposure=0.95, max_daily_loss=0.99
)


class _ConstantWeight(Strategy):
    """Holds a fixed target weight every bar (to test fractional sizing)."""

    name = "constant_weight"

    def __init__(self, weight: float) -> None:
        self.weight = weight

    def positions(self) -> pl.Expr:
        return pl.lit(self.weight)


class _IndexWeights(Strategy):
    """Target weight indexed by bar position — a scripted scale in/out path."""

    name = "index_weights"

    def __init__(self, weights: list[float]) -> None:
        self.weights = weights

    def positions(self) -> pl.Expr:
        idx = pl.int_range(pl.len())
        expr = pl.lit(0.0)
        for i, w in reversed(list(enumerate(self.weights))):
            expr = pl.when(idx == i).then(pl.lit(float(w))).otherwise(expr)
        return expr


def _flat_store(symbol: str, n: int, price: float = 100.0) -> FakeStore:
    """`n` daily bars at a constant price with deep volume (no cap/limit effects)."""
    store = FakeStore()
    start = datetime(2024, 1, 1, tzinfo=UTC)
    store.write_bars(
        [
            Bar(
                symbol=symbol,
                interval=Interval.DAY,
                timestamp=start + timedelta(days=i),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=10_000_000,
            )
            for i in range(n)
        ]
    )
    return store


def _store_from_closes(symbol: str, closes: list[float]) -> FakeStore:
    store = FakeStore()
    start = datetime(2024, 1, 1, tzinfo=UTC)
    store.write_bars(
        [
            Bar(
                symbol=symbol,
                interval=Interval.DAY,
                timestamp=start + timedelta(days=i),
                open=c,
                high=c + 0.5,
                low=c - 0.5,
                close=c,
                volume=1000,
            )
            for i, c in enumerate(closes)
        ]
    )
    return store


def test_event_driven_runs_and_reports() -> None:
    store = FakeStore()
    store.write_bars(make_bars("AAA", interval=Interval.DAY, count=60))
    result = EventDrivenBacktest(
        store, SmaCross(5, 20), cash=1_000_000, universe=["AAA"]
    ).run()
    assert result.data.height == 60
    assert result.data["equity"][0] > 0
    stats = result.stats()
    assert {"total_return", "sharpe", "max_drawdown", "calmar"} <= set(stats)


def test_entry_lags_one_bar_and_fills_at_open() -> None:
    # Bars with open != close so the fill venue is observable. Bar 1 is a big up
    # bar (opens 100, closes 200); BuyAndHold wants in from bar 0's close.
    store = FakeStore()
    start = datetime(2024, 1, 1, tzinfo=UTC)
    ohlc = [
        (100.0, 100.0, 100.0, 100.0),  # bar 0
        (100.0, 200.0, 100.0, 200.0),  # bar 1: open 100 -> close 200
        (200.0, 200.0, 200.0, 200.0),  # bar 2
    ]
    store.write_bars(
        [
            Bar(
                symbol="AAA",
                interval=Interval.DAY,
                timestamp=start + timedelta(days=i),
                open=o,
                high=h,
                low=low,
                close=c,
                volume=1000,
            )
            for i, (o, h, low, c) in enumerate(ohlc)
        ]
    )
    result = EventDrivenBacktest(
        store,
        BuyAndHold(),
        cash=100_000,
        universe=["AAA"],
        risk=RiskManager(RiskLimits(max_daily_loss=0.99)),
    ).run()
    eq = result.data["equity"].to_list()
    cash = result.data["cash"].to_list()

    # One-bar lag: BuyAndHold's bar-0 target is shifted out, so nothing trades on
    # bar 0 and equity is exactly the starting cash.
    assert eq[0] == 100_000
    # The entry executes on bar 1 (cash falls), filling at the OPEN (100). Marking
    # to bar 1's close (200) then shows a gain — a same-bar close fill (200) would
    # leave equity at starting cash minus costs instead.
    assert cash[1] < cash[0]
    assert eq[1] > eq[0]


def test_fractional_target_weight_sizes_partial() -> None:
    # A constant 0.5 target invests ~50% of equity, NOT all-in. (The old binary
    # engine treated any positive signal as full size — ~95% here — so this pins
    # the fix: sizing honours the weight.)
    store = _flat_store("AAA", n=4)
    result = EventDrivenBacktest(
        store,
        _ConstantWeight(0.5),
        cash=100_000,
        universe=["AAA"],
        risk=RiskManager(_WIDE),
    ).run()
    cash = result.data["cash"].to_list()
    # bar 0 lagged (no trade); from bar 1 on, ~¥50k is invested → ~¥50k cash left
    assert cash[0] == 100_000
    assert 49_000 < cash[-1] < 51_000


def test_target_weight_scales_in_and_out() -> None:
    # A rising-then-falling target makes the engine BUY the same name in tranches
    # and then SELL it down in tranches — multiple trades per name, the real-world
    # pattern the old all-or-nothing engine couldn't express. Weights are lagged
    # one bar, so trades land on bars 2-6.
    weights = [0.0, 0.2, 0.4, 0.6, 0.4, 0.2, 0.0]
    store = _flat_store("AAA", n=len(weights))
    result = EventDrivenBacktest(
        store,
        _IndexWeights(weights),
        cash=100_000,
        universe=["AAA"],
        risk=RiskManager(_WIDE),
    ).run()
    cash = result.data["cash"].to_list()
    # Scale IN (bars 2-4): each buy lowers cash; trough at the 0.6 peak (bar 4).
    assert cash[2] > cash[3] > cash[4]
    # Scale OUT (bars 5-6): each sell raises cash back up.
    assert cash[4] < cash[5] < cash[6]


def test_stop_loss_preserves_capital_on_crash() -> None:
    # rises a touch, then crashes hard and stays low
    closes = [100.0, 100.0, 94.0, 60.0, 60.0, 60.0]
    store = _store_from_closes("AAA", closes)

    # only difference is the stop; disable the daily-loss halt to isolate it
    with_stop = EventDrivenBacktest(
        store,
        BuyAndHold(),
        cash=100_000,
        universe=["AAA"],
        risk=RiskManager(RiskLimits(stop_loss=0.05, max_daily_loss=0.99)),
    ).run()
    no_stop = EventDrivenBacktest(
        store,
        BuyAndHold(),
        cash=100_000,
        universe=["AAA"],
        risk=RiskManager(RiskLimits(stop_loss=0.99, max_daily_loss=0.99)),
    ).run()

    # the stop exits near -5% instead of riding the position down to 60 — exactly
    # the path-dependent behaviour the vectorized engine cannot model
    assert with_stop.data["equity"][-1] > no_stop.data["equity"][-1]
