"""Unit tests for the execution layer (SimBroker, RiskManager, engine)."""

from __future__ import annotations

import pytest
from factories import make_bars
from fakes import FakeStore

from super_trade.backtest import NO_COSTS, BuyAndHold
from super_trade.backtest.costs import CostModel
from super_trade.data import Interval
from super_trade.execution import (
    ExecutionEngine,
    Order,
    RiskLimits,
    RiskManager,
    Side,
    SimBroker,
    daily_report,
)

# --- SimBroker -------------------------------------------------------------


def test_buy_deducts_cash_with_cost() -> None:
    broker = SimBroker(cash=100_000, costs=CostModel())
    fill = broker.place_order(Order("AAA", Side.BUY, 100, 50.0))
    assert fill is not None
    # notional 5000 + cost 5000*(0.00025+0.0001) = 5001.75
    assert broker.cash() == pytest.approx(100_000 - 5001.75)
    assert broker.shares("AAA") == 100


def test_buy_rejected_without_cash() -> None:
    broker = SimBroker(cash=1_000)
    assert broker.place_order(Order("AAA", Side.BUY, 100, 50.0)) is None


def test_orders_must_be_whole_lots() -> None:
    broker = SimBroker(cash=100_000)
    assert broker.place_order(Order("AAA", Side.BUY, 150, 50.0)) is None  # 1.5 lots


def test_sell_returns_cash_and_clears_position() -> None:
    broker = SimBroker(cash=100_000, costs=NO_COSTS)
    broker.place_order(Order("AAA", Side.BUY, 100, 50.0))
    broker.place_order(Order("AAA", Side.SELL, 100, 60.0))
    assert "AAA" not in broker.positions()
    assert broker.cash() == pytest.approx(100_000 - 5000 + 6000)


# --- RiskManager -----------------------------------------------------------


def test_stop_loss_threshold() -> None:
    from super_trade.execution import Position

    risk = RiskManager(RiskLimits(stop_loss=0.08))
    pos = Position("AAA", shares=100, avg_price=100.0)
    assert risk.stop_triggered(pos, 91.0) is True  # -9%
    assert risk.stop_triggered(pos, 93.0) is False  # -7%


def test_daily_loss_halt() -> None:
    risk = RiskManager(RiskLimits(max_daily_loss=0.05))
    risk.start_day(100_000)
    assert risk.update_daily_loss(96_000) is False
    assert risk.update_daily_loss(94_000) is True
    assert risk.can_trade() is False


def test_max_buy_shares_respects_caps() -> None:
    risk = RiskManager(RiskLimits(max_position_weight=0.2, max_gross_exposure=0.95))
    risk.start_day(100_000)
    broker = SimBroker(cash=100_000)
    # 20% of 100k = 20000 budget; at ¥50 -> 4 lots = 400 shares
    assert risk.max_buy_shares("AAA", 50.0, 100_000, broker) == 400


# --- ExecutionEngine -------------------------------------------------------


def _store_with(symbol: str, **kw) -> FakeStore:
    store = FakeStore()
    store.write_bars(make_bars(symbol=symbol, interval=Interval.DAY, count=30, **kw))
    return store


def test_engine_buys_on_signal() -> None:
    store = _store_with("AAA")
    broker = SimBroker(cash=100_000)
    risk = RiskManager()
    risk.start_day(100_000)
    engine = ExecutionEngine(
        broker, store, BuyAndHold(), risk, universe=["AAA"], dry_run=False
    )
    fills = engine.scan_once()
    assert any(f.side == Side.BUY for f in fills)
    assert broker.shares("AAA") > 0


def test_engine_stop_loss_exits() -> None:
    store = _store_with("AAA")  # closes ~100
    broker = SimBroker(cash=100_000)
    broker.place_order(Order("AAA", Side.BUY, 100, 200.0))  # entry far above market
    risk = RiskManager()
    risk.start_day(broker.cash() + 100 * 200)
    engine = ExecutionEngine(
        broker, store, BuyAndHold(), risk, universe=["AAA"], dry_run=False
    )
    fills = engine.scan_once()
    assert any(f.reason == "stop_loss" and f.side == Side.SELL for f in fills)
    assert "AAA" not in broker.positions()  # exited, and not re-bought same scan


def test_dry_run_places_no_orders() -> None:
    store = _store_with("AAA")
    broker = SimBroker(cash=100_000)
    risk = RiskManager()
    risk.start_day(100_000)
    engine = ExecutionEngine(
        broker, store, BuyAndHold(), risk, universe=["AAA"], dry_run=True
    )
    assert engine.scan_once() == []
    assert broker.cash() == 100_000  # untouched


def test_daily_report_renders() -> None:
    broker = SimBroker(cash=100_000)
    broker.place_order(Order("AAA", Side.BUY, 100, 50.0))
    report = daily_report(broker, broker.fills, {"AAA": 55.0}, date_label="2026-06-21")
    assert "Daily report 2026-06-21" in report
    assert "AAA" in report
