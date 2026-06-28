"""Tests for interval resampling (1-minute -> 5/15/30/60-min and daily)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest
from fakes import FakeStore

from super_trade.data import BAR_COLUMNS, Interval, load_bars, resample


def _minute_day(symbol: str = "X", base: float = 100.0) -> pl.DataFrame:
    """A full A-share day of 1-min bars: morning 01:30-03:29 + afternoon
    05:00-06:59 UTC (= 09:30-11:29 and 13:00-14:59 Beijing), 240 bars."""
    rows = []

    def session(start: datetime, n: int, b: float) -> None:
        for i in range(n):
            c = b + i * 0.1
            rows.append(
                {
                    "symbol": symbol,
                    "interval": "1m",
                    "timestamp": start + timedelta(minutes=i),
                    "open": c,
                    "high": c + 0.5,
                    "low": c - 0.5,
                    "close": c + 0.05,
                    "volume": 100 + i,
                }
            )

    session(datetime(2024, 1, 2, 1, 30, tzinfo=UTC), 120, base)
    session(datetime(2024, 1, 2, 5, 0, tzinfo=UTC), 120, base + 12.0)
    return pl.DataFrame(rows).select(BAR_COLUMNS)


def test_interval_helpers() -> None:
    assert Interval.THIRTY_MINUTE.minutes == 30
    assert Interval.HOUR.minutes == 60
    assert Interval.DAY.minutes == 1440
    assert Interval.MINUTE.is_intraday and not Interval.DAY.is_intraday


def test_bar_counts() -> None:
    df = _minute_day()
    assert resample(df, Interval.FIVE_MINUTE).height == 48  # 240 / 5
    assert resample(df, Interval.FIFTEEN_MINUTE).height == 16
    assert resample(df, Interval.THIRTY_MINUTE).height == 8
    assert resample(df, Interval.HOUR).height == 4
    assert resample(df, Interval.DAY).height == 1


def test_hourly_bars_respect_sessions() -> None:
    # 60-min must be 09:30/10:30/13:00/14:00 Beijing (01:30/02:30/05:00/06:00 UTC),
    # NOT 09:00/10:00 — i.e. never merged across the lunch break.
    r = resample(_minute_day(), Interval.HOUR)
    got = [t.strftime("%H:%M") for t in r["timestamp"].to_list()]
    assert got == ["01:30", "02:30", "05:00", "06:00"]
    assert (r["interval"] == "1h").all()


def test_ohlcv_aggregation() -> None:
    r = resample(_minute_day(base=100.0), Interval.FIVE_MINUTE)
    first = r.row(0, named=True)  # bars i=0..4 of the morning
    assert first["open"] == pytest.approx(100.0)  # first
    assert first["high"] == pytest.approx(100.9)  # max (i=4: 100.4 + 0.5)
    assert first["low"] == pytest.approx(99.5)  # min (i=0: 100.0 - 0.5)
    assert first["close"] == pytest.approx(100.45)  # last (i=4: 100.4 + 0.05)
    assert first["volume"] == 100 + 101 + 102 + 103 + 104


def test_daily_label_and_close() -> None:
    r = resample(_minute_day(base=100.0), Interval.DAY)
    row = r.row(0, named=True)
    assert row["timestamp"] == datetime(2024, 1, 2, tzinfo=UTC)  # UTC midnight
    assert row["open"] == pytest.approx(100.0)
    assert row["close"] == pytest.approx(123.95)  # last afternoon close


def test_multi_symbol_panel() -> None:
    panel = pl.concat([_minute_day("A"), _minute_day("B")])
    r = resample(panel, Interval.THIRTY_MINUTE)
    assert r.height == 16  # 8 per symbol
    assert set(r["symbol"].unique().to_list()) == {"A", "B"}


def test_resample_to_finer_raises() -> None:
    with pytest.raises(ValueError, match="finer"):
        resample(_minute_day(), Interval.MINUTE, source=Interval.FIVE_MINUTE)


def test_load_bars_resamples_from_minute() -> None:
    store = FakeStore()
    store.write_bars(_minute_day("X"))
    direct = load_bars(store, "X", Interval.MINUTE)
    assert direct.height == 240
    five = load_bars(store, "X", Interval.FIVE_MINUTE, resample_from=Interval.MINUTE)
    assert five.height == 48
    assert five.columns == list(BAR_COLUMNS)
