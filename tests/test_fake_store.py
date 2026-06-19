"""Unit tests for the DataStore contract, exercised via the in-memory FakeStore."""

from __future__ import annotations

from collections.abc import Callable

from fakes import FakeStore

from super_trade.data import Bar, Interval


def test_write_read_roundtrip(
    fake_store: FakeStore, synthetic_bars: Callable[..., list[Bar]]
) -> None:
    bars = synthetic_bars(symbol="MOCK", interval=Interval.MINUTE, count=10)
    assert fake_store.write_bars(bars) == 10

    df = fake_store.read_bars("MOCK", Interval.MINUTE)
    assert df.height == 10
    assert df.columns == [
        "symbol",
        "interval",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    timestamps = df["timestamp"].to_list()
    assert timestamps == sorted(timestamps)


def test_dedup_on_repeated_write(
    fake_store: FakeStore, synthetic_bars: Callable[..., list[Bar]]
) -> None:
    bars = synthetic_bars(count=5)
    fake_store.write_bars(bars)
    fake_store.write_bars(bars)  # same keys again
    assert fake_store.read_bars("MOCK", Interval.MINUTE).height == 5


def test_time_filter_is_half_open(
    fake_store: FakeStore, synthetic_bars: Callable[..., list[Bar]]
) -> None:
    bars = synthetic_bars(count=10)
    fake_store.write_bars(bars)
    df = fake_store.read_bars(
        "MOCK", Interval.MINUTE, start=bars[2].timestamp, end=bars[5].timestamp
    )
    assert df.height == 3  # indices 2, 3, 4 (end exclusive)


def test_list_symbols(
    fake_store: FakeStore, synthetic_bars: Callable[..., list[Bar]]
) -> None:
    fake_store.write_bars(synthetic_bars(symbol="AAA", count=2))
    fake_store.write_bars(synthetic_bars(symbol="BBB", count=2))
    assert fake_store.list_symbols() == ["AAA", "BBB"]
    assert fake_store.list_symbols(interval=Interval.DAY) == []


def test_read_empty_returns_typed_frame(fake_store: FakeStore) -> None:
    df = fake_store.read_bars("NONE", Interval.MINUTE)
    assert df.height == 0
    assert "close" in df.columns


def test_latest_timestamp(
    fake_store: FakeStore, synthetic_bars: Callable[..., list[Bar]]
) -> None:
    assert fake_store.latest_timestamp("MOCK", Interval.MINUTE) is None
    bars = synthetic_bars(count=10)
    fake_store.write_bars(bars)
    assert fake_store.latest_timestamp("MOCK", Interval.MINUTE) == bars[-1].timestamp
    # different interval has nothing stored
    assert fake_store.latest_timestamp("MOCK", Interval.DAY) is None
