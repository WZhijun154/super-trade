"""Integration tests against a real ClickHouse server.

Marked ``integration`` and run against the isolated ``super_trade_test`` database
(see conftest). Mock data here never reaches the real ``super_trade`` DB. These are
auto-skipped when no server is reachable.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from factories import make_bars

from super_trade.data import Bar, ClickHouseStore, Interval

pytestmark = pytest.mark.integration


def test_write_read_roundtrip(
    clean_clickhouse: ClickHouseStore, synthetic_bars: Callable[..., list[Bar]]
) -> None:
    store = clean_clickhouse
    bars = synthetic_bars(symbol="MOCK", interval=Interval.MINUTE, count=10)
    assert store.write_bars(bars) == 10

    df = store.read_bars("MOCK", Interval.MINUTE)
    assert df.height == 10
    assert df["symbol"].unique().to_list() == ["MOCK"]
    timestamps = df["timestamp"].to_list()
    assert timestamps == sorted(timestamps)


def test_replacingmergetree_dedup_on_reingest(
    clean_clickhouse: ClickHouseStore,
) -> None:
    store = clean_clickhouse
    bars = make_bars(symbol="MOCK", interval=Interval.MINUTE, count=5)
    store.write_bars(bars)
    store.write_bars(bars)  # re-ingest identical keys
    # read_bars uses FINAL, so duplicates collapse even before a background merge
    assert store.read_bars("MOCK", Interval.MINUTE).height == 5


def test_time_filter(clean_clickhouse: ClickHouseStore) -> None:
    store = clean_clickhouse
    bars = make_bars(count=10)
    store.write_bars(bars)
    df = store.read_bars(
        "MOCK", Interval.MINUTE, start=bars[2].timestamp, end=bars[5].timestamp
    )
    assert df.height == 3


def test_polars_write_path(clean_clickhouse: ClickHouseStore) -> None:
    import polars as pl

    store = clean_clickhouse
    bars = make_bars(symbol="VIAPL", count=4)
    df = pl.DataFrame(
        {
            "symbol": [b.symbol for b in bars],
            "interval": [b.interval.value for b in bars],
            "timestamp": [b.timestamp for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
        }
    )
    assert store.write_bars(df) == 4
    assert store.read_bars("VIAPL", Interval.MINUTE).height == 4
