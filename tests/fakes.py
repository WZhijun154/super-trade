"""In-memory :class:`DataStore` for fast unit tests (no ClickHouse required).

TEST ONLY. Lives under ``tests/`` so application/backtest code cannot import it.
Mimics the ClickHouse store's observable contract: dedup by
``(symbol, interval, timestamp)`` keeping the last write, half-open ``[start, end)``
time filtering, and time-ordered reads.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import polars as pl

from super_trade.data import BAR_COLUMNS, Bar, Interval
from super_trade.data.store import DataStore


class FakeStore(DataStore):
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str, datetime], dict] = {}
        self.initialized = False

    def init_schema(self) -> None:
        self.initialized = True

    def write_bars(self, bars: Iterable[Bar] | pl.DataFrame) -> int:
        rows = self._normalize(bars)
        for r in rows:
            self._rows[(r["symbol"], r["interval"], r["timestamp"])] = r
        return len(rows)

    def read_bars(
        self,
        symbol: str,
        interval: Interval,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pl.DataFrame:
        rows = [
            r
            for r in self._rows.values()
            if r["symbol"] == symbol
            and r["interval"] == interval.value
            and (start is None or r["timestamp"] >= start)
            and (end is None or r["timestamp"] < end)
        ]
        rows.sort(key=lambda r: r["timestamp"])
        return pl.DataFrame(rows, schema=list(BAR_COLUMNS))

    def latest_timestamp(self, symbol: str, interval: Interval) -> datetime | None:
        stamps = [
            r["timestamp"]
            for r in self._rows.values()
            if r["symbol"] == symbol and r["interval"] == interval.value
        ]
        return max(stamps) if stamps else None

    def list_symbols(self, interval: Interval | None = None) -> list[str]:
        return sorted(
            {
                r["symbol"]
                for r in self._rows.values()
                if interval is None or r["interval"] == interval.value
            }
        )

    def close(self) -> None:
        self._rows.clear()

    @staticmethod
    def _normalize(bars: Iterable[Bar] | pl.DataFrame) -> list[dict]:
        if isinstance(bars, pl.DataFrame):
            return bars.select(BAR_COLUMNS).to_dicts()
        return [
            {
                "symbol": b.symbol,
                "interval": b.interval.value,
                "timestamp": b.timestamp,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ]
