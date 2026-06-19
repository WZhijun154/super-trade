"""Unit tests for DailyBackfill cache/skip logic (offline, no network)."""

from __future__ import annotations

from datetime import datetime

from factories import make_bars
from fakes import FakeStore

from super_trade.data import Bar, Interval
from super_trade.ingest import DailyBackfill
from super_trade.sources.base import Adjust, DataSource, SymbolInfo


class FakeSource(DataSource):
    """A DataSource that replays canned bars and records how it was called."""

    def __init__(self, bars_by_symbol: dict[str, list[Bar]]) -> None:
        self._bars = bars_by_symbol
        self.calls: list[tuple[str, datetime | None]] = []

    def list_symbols(self) -> list[SymbolInfo]:
        return [SymbolInfo(symbol=s, name=s) for s in self._bars]

    def fetch_bars(
        self,
        symbol: str,
        interval: Interval,
        start: datetime | None = None,
        end: datetime | None = None,
        adjust: Adjust = Adjust.HFQ,
    ) -> list[Bar]:
        self.calls.append((symbol, start))
        return list(self._bars.get(symbol, []))


def _daily_bars(symbol: str, count: int) -> list[Bar]:
    return make_bars(symbol=symbol, interval=Interval.DAY, count=count)


def test_first_run_writes_all_then_second_run_skips() -> None:
    bars = _daily_bars("MOCK", 5)
    source = FakeSource({"MOCK": bars})
    store = FakeStore()
    backfill = DailyBackfill(source, store)

    first = backfill.run(["MOCK"])
    assert (first.synced, first.skipped, first.rows) == (1, 0, 5)

    # Second run: store already has everything, nothing newer -> skip, no write.
    second = backfill.run(["MOCK"])
    assert (second.synced, second.skipped, second.rows) == (0, 1, 0)


def test_incremental_fetch_starts_from_cache() -> None:
    bars = _daily_bars("MOCK", 5)
    source = FakeSource({"MOCK": bars})
    store = FakeStore()
    backfill = DailyBackfill(source, store, lookback_days=3)

    backfill.run(["MOCK"])  # populates store
    backfill.run(["MOCK"])  # incremental

    # First call had no cache (start == configured epoch); second started near the
    # latest stored bar (latest - lookback), not from the epoch.
    first_start = source.calls[0][1]
    second_start = source.calls[1][1]
    assert first_start is not None and first_start.year == 1990
    assert second_start is not None and second_start > bars[0].timestamp


def test_force_refetches_ignoring_cache() -> None:
    bars = _daily_bars("MOCK", 5)
    source = FakeSource({"MOCK": bars})
    store = FakeStore()
    backfill = DailyBackfill(source, store)

    backfill.run(["MOCK"])
    forced = backfill.run(["MOCK"], force=True)
    assert forced.synced == 1 and forced.rows == 5
    assert source.calls[1][1] is not None and source.calls[1][1].year == 1990


def test_failure_is_isolated_per_symbol() -> None:
    class Boom(FakeSource):
        def fetch_bars(self, symbol, interval, start=None, end=None, adjust=Adjust.HFQ):  # type: ignore[override]
            if symbol == "BAD":
                raise ConnectionError("boom")
            return super().fetch_bars(symbol, interval, start, end, adjust)

    source = Boom({"GOOD": _daily_bars("GOOD", 3), "BAD": []})
    store = FakeStore()
    report = DailyBackfill(source, store).run(["GOOD", "BAD"])
    assert report.synced == 1
    assert report.failed == 1
    assert "BAD" in report.failures
