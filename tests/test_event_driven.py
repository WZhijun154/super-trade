"""Tests for the event-driven backtest (replay through SimBroker)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from factories import make_bars
from fakes import FakeStore

from super_trade.backtest import BuyAndHold, SmaCross
from super_trade.data import Bar, Interval
from super_trade.execution import EventDrivenBacktest, RiskLimits, RiskManager


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
