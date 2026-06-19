"""Source-agnostic market-data acquisition interface.

Ingestion code depends on :class:`DataSource`, not a concrete provider. akshare is
the first implementation; QMT (recent/precise data) can be added later behind the
same interface without touching the orchestrator or storage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from super_trade.data import Bar, Interval


class Adjust(StrEnum):
    """Price-adjustment mode. ``HFQ`` (backward) keeps history stable over time and
    is the right default for backtesting; ``QFQ`` (forward) drifts as new data
    arrives; ``NONE`` is raw/unadjusted."""

    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


class SymbolInfo(BaseModel):
    """A tradable instrument's identifier and display name."""

    symbol: str
    name: str


class DataSource(ABC):
    """Abstract provider of market data."""

    @abstractmethod
    def list_symbols(self) -> list[SymbolInfo]:
        """Return the full investable universe this source can serve."""

    @abstractmethod
    def fetch_bars(
        self,
        symbol: str,
        interval: Interval,
        start: datetime | None = None,
        end: datetime | None = None,
        adjust: Adjust = Adjust.HFQ,
    ) -> list[Bar]:
        """Return validated bars for ``symbol`` in ``[start, end]``.

        Implementations apply their own throttling/retries and skip individual
        malformed rows rather than failing the whole request.
        """
