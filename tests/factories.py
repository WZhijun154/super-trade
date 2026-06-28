"""Synthetic market-data generators for TESTS ONLY.

WARNING: This produces fabricated OHLCV data. Never import it from application or
backtest code — backtests must read real data from a DataStore. Keeping these
generators under ``tests/`` makes that violation impossible by construction (the
package does not depend on the test tree).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from super_trade.data import Bar, Interval

_INTERVAL_DELTA: dict[Interval, timedelta] = {
    Interval.MINUTE: timedelta(minutes=1),
    Interval.FIVE_MINUTE: timedelta(minutes=5),
    Interval.FIFTEEN_MINUTE: timedelta(minutes=15),
    Interval.THIRTY_MINUTE: timedelta(minutes=30),
    Interval.HOUR: timedelta(hours=1),
    Interval.DAY: timedelta(days=1),
}


def make_bars(
    symbol: str = "MOCK",
    interval: Interval = Interval.MINUTE,
    count: int = 10,
    start: datetime | None = None,
    base_price: float = 100.0,
) -> list[Bar]:
    """Return ``count`` deterministic, validation-passing synthetic bars."""
    start = start or datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    delta = _INTERVAL_DELTA[interval]
    bars: list[Bar] = []
    price = base_price
    for i in range(count):
        open_ = price
        close = price + ((i % 3) - 1)  # deterministic -1/0/+1 drift
        high = max(open_, close) + 0.5
        low = min(open_, close) - 0.5
        bars.append(
            Bar(
                symbol=symbol,
                interval=interval,
                timestamp=start + delta * i,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=1000 + i * 10,
            )
        )
        price = close
    return bars
