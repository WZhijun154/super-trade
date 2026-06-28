"""Seed the `super_trade_sandbox` ClickHouse DB with realistic synthetic bars.

SANDBOX / EXPLORATION ONLY. This generates fabricated OHLCV via a geometric
random walk — it is NOT real market data and must never be used for backtests.
It writes to a dedicated `super_trade_sandbox` database so it can never pollute
the real `super_trade` data. Drop it anytime: DROP DATABASE super_trade_sandbox SYNC.

Run:
    uv run python scripts/seed_sandbox.py            # daily bars (resets the table)
    uv run python scripts/seed_sandbox.py minute     # 1-minute bars (additive)
"""

from __future__ import annotations

import math
import random
import sys
from datetime import UTC, datetime, timedelta

from super_trade.data import Bar, ClickHouseConfig, ClickHouseStore, Interval

# Realistic-ish parameters for a daily equity series.
_ANNUAL_DRIFT = 0.08
_ANNUAL_VOL = 0.32
_TRADING_DAYS = 252
_DT = 1.0 / _TRADING_DAYS
_MINUTES_PER_DAY = 240  # A-share: 4 trading hours


def generate_daily_bars(
    symbol: str,
    *,
    count: int = 500,
    start: datetime,
    base_price: float,
    seed: int,
    base_volume: int = 1_000_000,
) -> list[Bar]:
    """Generate `count` realistic daily bars via geometric Brownian motion."""
    rng = random.Random(seed)
    sigma_d = _ANNUAL_VOL * math.sqrt(_DT)
    mu_d = (_ANNUAL_DRIFT - 0.5 * _ANNUAL_VOL**2) * _DT

    bars: list[Bar] = []
    prev_close = base_price
    day = start
    while len(bars) < count:
        if day.weekday() < 5:  # Mon-Fri only (rough trading calendar)
            # overnight gap, then the day's log return
            gap = rng.gauss(0, sigma_d * 0.4)
            open_ = prev_close * math.exp(gap)
            ret = rng.gauss(mu_d, sigma_d)
            close = open_ * math.exp(ret)
            # intraday extremes around the open/close envelope
            hi = max(open_, close) * (1 + abs(rng.gauss(0, sigma_d * 0.7)))
            lo = min(open_, close) * (1 - abs(rng.gauss(0, sigma_d * 0.7)))
            # volume rises with the size of the move
            vol = base_volume * math.exp(rng.gauss(0, 0.35)) * (1 + 6 * abs(ret))

            bars.append(
                Bar(
                    symbol=symbol,
                    interval=Interval.DAY,
                    timestamp=datetime(day.year, day.month, day.day, tzinfo=UTC),
                    open=round(open_, 2),
                    high=round(hi, 2),
                    low=round(lo, 2),
                    close=round(close, 2),
                    volume=int(vol),
                )
            )
            prev_close = close
        day += timedelta(days=1)
    return bars


def generate_minute_bars(
    symbol: str,
    *,
    days: int = 5,
    start: datetime,
    base_price: float,
    seed: int,
    base_volume: int = 20_000,
) -> list[Bar]:
    """Generate session-aware 1-minute bars for `days` trading days.

    Each day has the two A-share sessions: 09:30-11:29 and 13:00-14:59 Beijing,
    i.e. 01:30-03:29 and 05:00-06:59 UTC — 240 one-minute bars per day.
    """
    rng = random.Random(seed)
    sigma_m = _ANNUAL_VOL * math.sqrt(_DT / _MINUTES_PER_DAY)

    bars: list[Bar] = []
    prev_close = base_price
    day = start
    seeded = 0
    while seeded < days:
        if day.weekday() < 5:  # Mon-Fri
            for hour, minute in ((1, 30), (5, 0)):  # morning, afternoon (UTC)
                session_start = datetime(
                    day.year, day.month, day.day, hour, minute, tzinfo=UTC
                )
                for k in range(120):
                    open_ = prev_close
                    close = open_ * math.exp(rng.gauss(0, sigma_m))
                    hi = max(open_, close) * (1 + abs(rng.gauss(0, sigma_m * 0.5)))
                    lo = min(open_, close) * (1 - abs(rng.gauss(0, sigma_m * 0.5)))
                    bars.append(
                        Bar(
                            symbol=symbol,
                            interval=Interval.MINUTE,
                            timestamp=session_start + timedelta(minutes=k),
                            open=round(open_, 2),
                            high=round(hi, 2),
                            low=round(lo, 2),
                            close=round(close, 2),
                            volume=max(
                                int(base_volume * math.exp(rng.gauss(0, 0.4))), 1
                            ),
                        )
                    )
                    prev_close = close
            seeded += 1
        day += timedelta(days=1)
    return bars


def _seed_minute(store: ClickHouseStore) -> None:
    """Seed 1-minute bars for a couple of symbols (additive — no truncate)."""
    minute_universe = {"FAKE001": 100.0, "FAKE002": 38.5}
    total = 0
    for i, (sym, price) in enumerate(minute_universe.items()):
        bars = generate_minute_bars(
            sym,
            days=5,
            start=datetime(2024, 1, 2, tzinfo=UTC),
            base_price=price,
            seed=500 + i,
        )
        total += store.write_bars(bars)
    print(f"seeded {total} 1-minute bars across {len(minute_universe)} symbols")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "minute":
        store = ClickHouseStore(ClickHouseConfig(database="super_trade_sandbox"))
        with store:
            store.init_schema()
            _seed_minute(store)
        return

    universe = {
        "FAKE001": (100.0, 1_200_000),
        "FAKE002": (38.5, 4_500_000),
        "FAKE003": (256.0, 600_000),
        "FAKE004": (12.8, 9_000_000),
        "FAKE005": (1680.0, 90_000),
    }
    start = datetime(2023, 1, 2, tzinfo=UTC)

    store = ClickHouseStore(ClickHouseConfig(database="super_trade_sandbox"))
    with store:
        store.init_schema()
        store.client.command(f"TRUNCATE TABLE IF EXISTS {store._config.database}.bars")
        total = 0
        for i, (sym, (price, base_vol)) in enumerate(universe.items()):
            bars = generate_daily_bars(
                sym,
                count=500,
                start=start,
                base_price=price,
                seed=1000 + i,
                base_volume=base_vol,
            )
            total += store.write_bars(bars)
        print(f"seeded {total} bars across {len(universe)} symbols")
        print("symbols:", store.list_symbols())


if __name__ == "__main__":
    main()
