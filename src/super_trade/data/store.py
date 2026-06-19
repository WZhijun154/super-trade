"""Backend-agnostic storage interface.

Code that reads or writes market data should depend on :class:`DataStore`, not on
a concrete backend. This keeps the rest of the system decoupled from ClickHouse,
makes it trivially testable with an in-memory fake, and leaves room to swap or add
backends later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime

import polars as pl

from .models import Bar, Interval


class DataStore(ABC):
    """Abstract market-data store.

    Implementations are expected to be safe to use as a context manager so
    connections are released deterministically.
    """

    @abstractmethod
    def init_schema(self) -> None:
        """Create the database/tables if they do not already exist (idempotent)."""

    @abstractmethod
    def write_bars(self, bars: Iterable[Bar] | pl.DataFrame) -> int:
        """Bulk-insert bars. Returns the number of rows written.

        Accepts either validated :class:`Bar` objects or a Polars DataFrame whose
        columns match :data:`super_trade.data.models.BAR_COLUMNS`. Re-ingesting an
        overlapping range is safe (the backend deduplicates on merge).
        """

    @abstractmethod
    def read_bars(
        self,
        symbol: str,
        interval: Interval,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pl.DataFrame:
        """Return bars for ``symbol``/``interval`` in ``[start, end)``, time-ordered.

        ``start``/``end`` are optional bounds; ``None`` means unbounded on that side.
        """

    @abstractmethod
    def latest_timestamp(self, symbol: str, interval: Interval) -> datetime | None:
        """Return the most recent stored timestamp for ``symbol``/``interval``.

        Returns ``None`` when nothing is stored. Used by ingestion to fetch only
        the missing tail instead of re-downloading existing data.
        """

    @abstractmethod
    def list_symbols(self, interval: Interval | None = None) -> list[str]:
        """Return the distinct symbols present, optionally filtered by interval."""

    @abstractmethod
    def close(self) -> None:
        """Release any underlying resources/connections."""

    def __enter__(self) -> DataStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
