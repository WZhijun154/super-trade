"""Tests for A-share market realism in the event-driven backtest.

Covers the four rules layered onto the engine: T+1, 涨跌停 price limits, 停牌
suspension, and the volume-based partial-fill cap. Each builds tiny daily bars
with `open != close` / specific volumes so the rule's effect is observable, and
where useful compares a realistic run against one with the rule disabled.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fakes import FakeStore

from super_trade.backtest import BuyAndHold
from super_trade.data import Bar, Interval
from super_trade.execution import (
    EventDrivenBacktest,
    MarketRules,
    RiskLimits,
    RiskManager,
    limit_pct,
)

# Risk limits that let a position go nearly all-in, so a crash/cap dominates the
# result instead of being muted by the default 20% per-name cap. Daily-loss halt
# is effectively off (0.99) so it never interferes with these scenarios.
_ALLIN = RiskLimits(
    max_position_weight=0.95,
    max_gross_exposure=0.95,
    max_daily_loss=0.99,
    stop_loss=0.08,
)


def _store(
    symbol: str, bars: list[tuple[float, float, float, float, int]]
) -> FakeStore:
    """Build a FakeStore of daily bars from (open, high, low, close, vol) rows."""
    store = FakeStore()
    start = datetime(2024, 1, 1, tzinfo=UTC)
    store.write_bars(
        [
            Bar(
                symbol=symbol,
                interval=Interval.DAY,
                timestamp=start + timedelta(days=i),
                open=o,
                high=h,
                low=low,
                close=c,
                volume=v,
            )
            for i, (o, h, low, c, v) in enumerate(bars)
        ]
    )
    return store


def test_limit_pct_by_board_prefix() -> None:
    assert limit_pct("688981") == 0.20  # STAR
    assert limit_pct("300750") == 0.20  # ChiNext
    assert limit_pct("600519") == 0.10  # SH main board
    assert limit_pct("000001") == 0.10  # SZ main board
    assert limit_pct("830799") == 0.30  # Beijing
    assert limit_pct("920819") == 0.30  # Beijing (92x)
    assert limit_pct("FAKE001") == 0.10  # non-numeric → default


def _intraday_store(
    symbol: str, bars: list[tuple[datetime, float, float, float, float, int]]
) -> FakeStore:
    """Build a FakeStore of 1-minute bars from explicit (ts, o, h, l, c, vol)."""
    store = FakeStore()
    store.write_bars(
        [
            Bar(
                symbol=symbol,
                interval=Interval.MINUTE,
                timestamp=ts,
                open=o,
                high=h,
                low=low,
                close=c,
                volume=v,
            )
            for ts, o, h, low, c, v in bars
        ]
    )
    return store


def test_t_plus_1_traps_same_day_stop() -> None:
    # T+1 only bites *intraday*: the buy and the would-be exit fall on the same
    # calendar day. Buy at 09:31, crash at 09:32 (stop wants to fire) — T+1 can't
    # sell today's purchase, so it's trapped; next day it recovers. Without T+1 it
    # sells the dip at 80 and locks in the loss. So the T+1 run ends *higher*.
    # (On daily bars T+1 would never trigger: the earliest exit is the next bar =
    # next day, which is already T+1-clear.)
    d1 = datetime(2024, 1, 2, tzinfo=UTC)
    d2 = datetime(2024, 1, 3, tzinfo=UTC)
    bars = [
        (d1, 100.0, 100.0, 100.0, 100.0, 1_000_000),  # 09:30 — lagged, no trade
        (d1 + timedelta(minutes=1), 100.0, 100.0, 100.0, 100.0, 1_000_000),  # buy @100
        (d1 + timedelta(minutes=2), 100.0, 100.0, 80.0, 80.0, 1_000_000),  # crash to 80
        (d2, 100.0, 100.0, 100.0, 100.0, 1_000_000),  # next day — recover to 100
    ]

    def run(t_plus_1: bool) -> float:
        store = _intraday_store("AAA", bars)
        result = EventDrivenBacktest(
            store,
            BuyAndHold(),
            cash=100_000,
            universe=["AAA"],
            interval=Interval.MINUTE,
            risk=RiskManager(_ALLIN),
            rules=MarketRules(t_plus_1=t_plus_1),
        ).run()
        return float(result.data["equity"].to_list()[-1])

    trapped = run(True)
    free = run(False)
    assert trapped > free  # T+1 forced the hold, which recovered


def test_limit_up_blocks_buy() -> None:
    # Every bar opens locked limit-up (each open == prev close x 1.10), so a
    # would-be buyer can never get filled — no position is ever taken.
    bars = [
        (100.0, 100.0, 100.0, 100.0, 1_000_000),  # day0 ref close 100
        (110.0, 110.0, 110.0, 110.0, 1_000_000),  # day1 +10% limit-up
        (121.0, 121.0, 121.0, 121.0, 1_000_000),  # day2 +10% limit-up
    ]
    store = _store("AAA", bars)
    result = EventDrivenBacktest(
        store, BuyAndHold(), cash=100_000, universe=["AAA"], risk=RiskManager(_ALLIN)
    ).run()
    # never bought → cash untouched on every bar
    assert all(c == 100_000 for c in result.data["cash"].to_list())


def test_suspension_blocks_fills() -> None:
    # volume == 0 means 停牌: no fills. With the cap disabled to isolate the rule,
    # suspension on → never buys; suspension off → buys (cash drops).
    bars = [
        (100.0, 100.0, 100.0, 100.0, 1_000_000),  # day0 — lagged, no trade
        (100.0, 100.0, 100.0, 100.0, 0),  # day1 — suspended
        (100.0, 100.0, 100.0, 100.0, 0),  # day2 — suspended
    ]

    def final_cash(enforce: bool) -> float:
        store = _store("AAA", bars)
        result = EventDrivenBacktest(
            store,
            BuyAndHold(),
            cash=100_000,
            universe=["AAA"],
            risk=RiskManager(_ALLIN),
            rules=MarketRules(enforce_suspension=enforce, participation_rate=0.0),
        ).run()
        return float(result.data["cash"].to_list()[-1])

    assert final_cash(True) == 100_000  # suspended → never filled
    assert final_cash(False) < 100_000  # allowed → bought


def test_volume_cap_partial_fill() -> None:
    # Bar volume 5000 shares, 10% participation → at most 500 shares (5 lots),
    # even though risk would allow ~900. Confirm only 5 lots are bought.
    bars = [
        (100.0, 100.0, 100.0, 100.0, 1_000_000),  # day0 — lagged, no trade
        (100.0, 100.0, 100.0, 100.0, 5_000),  # day1 — thin bar
        (100.0, 100.0, 100.0, 100.0, 1_000_000),  # day2
    ]
    store = _store("AAA", bars)
    result = EventDrivenBacktest(
        store,
        BuyAndHold(),
        cash=100_000,
        universe=["AAA"],
        risk=RiskManager(_ALLIN),
        rules=MarketRules(participation_rate=0.10),
    ).run()
    # spent ~ 500 shares x 100 yuan (+ small cost) -> 5 lots; round() absorbs costs
    cash_after = result.data["cash"].to_list()[1]
    lots = round((100_000 - cash_after) / (100 * 100))
    assert lots == 5
