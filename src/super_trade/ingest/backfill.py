"""Single-process daily backfill orchestrator.

Walks the investable universe and syncs each symbol's daily bars into a
:class:`DataStore`. The store is the cache: ``latest_timestamp`` tells us how far a
symbol is already loaded, so we only fetch the missing tail (plus a small lookback
to recapture late corrections). Writes are idempotent via the store's
``ReplacingMergeTree``, so interrupted or repeated runs are safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import logfire

from super_trade.data import DataStore, Interval
from super_trade.sources.base import Adjust, DataSource

_SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass
class BackfillReport:
    """Outcome of a backfill run."""

    total: int = 0
    synced: int = 0
    skipped: int = 0
    failed: int = 0
    rows: int = 0
    failures: dict[str, str] = field(default_factory=dict)


class DailyBackfill:
    """Sync daily bars for a universe of symbols, incrementally and idempotently."""

    def __init__(
        self,
        source: DataSource,
        store: DataStore,
        *,
        interval: Interval = Interval.DAY,
        adjust: Adjust = Adjust.HFQ,
        start: datetime | None = None,
        lookback_days: int = 5,
    ) -> None:
        self._source = source
        self._store = store
        self._interval = interval
        self._adjust = adjust
        self._start = start or datetime(1990, 1, 1, tzinfo=UTC)
        self._lookback = timedelta(days=lookback_days)

    def run(
        self, symbols: list[str] | None = None, *, force: bool = False
    ) -> BackfillReport:
        """Backfill ``symbols`` (or the whole universe). ``force`` ignores the cache."""
        self._store.init_schema()
        if symbols is None:
            symbols = [s.symbol for s in self._source.list_symbols()]

        report = BackfillReport(total=len(symbols))
        end = datetime.now(tz=_SHANGHAI)
        with logfire.span(
            "daily_backfill", total=len(symbols), adjust=self._adjust.value
        ):
            for i, symbol in enumerate(symbols, 1):
                try:
                    written = self._sync_one(symbol, end, force=force)
                    if written == 0:
                        report.skipped += 1
                    else:
                        report.synced += 1
                        report.rows += written
                    logfire.debug(
                        "synced {symbol}",
                        symbol=symbol,
                        index=i,
                        total=len(symbols),
                        rows=written,
                    )
                except Exception as exc:
                    report.failed += 1
                    report.failures[symbol] = str(exc)
                    logfire.error(
                        "backfill failed for {symbol}", symbol=symbol, error=str(exc)
                    )
        logfire.info(
            "backfill complete",
            total=report.total,
            synced=report.synced,
            skipped=report.skipped,
            failed=report.failed,
            rows=report.rows,
        )
        return report

    def _sync_one(self, symbol: str, end: datetime, *, force: bool) -> int:
        latest = None if force else self._store.latest_timestamp(symbol, self._interval)
        start = self._start if latest is None else latest - self._lookback
        bars = self._source.fetch_bars(
            symbol,
            self._interval,
            start=start,
            end=end,
            adjust=self._adjust,
        )
        if not bars:
            return 0
        # Already up to date: nothing newer than what we have — skip the write.
        if latest is not None and not any(b.timestamp > latest for b in bars):
            return 0
        return self._store.write_bars(bars)


def main() -> None:
    """Run a full daily backfill using env-configured ClickHouse + akshare."""
    from super_trade.data import ClickHouseConfig, ClickHouseStore
    from super_trade.observability import configure_logfire
    from super_trade.sources.akshare_source import AkshareSource

    configure_logfire()
    source = AkshareSource()
    with ClickHouseStore(ClickHouseConfig()) as store:
        DailyBackfill(source, store).run()


if __name__ == "__main__":
    main()
