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
