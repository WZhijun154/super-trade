"""Typed domain models for market data.

These Pydantic models define and validate the shape of data as it enters the
system (e.g. when parsing a provider's API response). They are deliberately
decoupled from storage: the store layer accepts/returns these models or columnar
frames, but the models themselves know nothing about ClickHouse.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator


class Interval(StrEnum):
    """Bar aggregation interval. The string value is what is persisted.

    1-minute is the finest grain; coarser intervals are derived by resampling
    (see :func:`super_trade.data.resample.resample`).
    """

    MINUTE = "1m"
    FIVE_MINUTE = "5m"
    FIFTEEN_MINUTE = "15m"
    THIRTY_MINUTE = "30m"
    HOUR = "1h"
    DAY = "1d"

    @property
    def minutes(self) -> int:
        """Length of one bar in minutes (``1d`` = a full 1440-minute day)."""
        return {
            Interval.MINUTE: 1,
            Interval.FIVE_MINUTE: 5,
            Interval.FIFTEEN_MINUTE: 15,
            Interval.THIRTY_MINUTE: 30,
            Interval.HOUR: 60,
            Interval.DAY: 1440,
        }[self]

    @property
    def is_intraday(self) -> bool:
        """True for everything finer than a daily bar."""
        return self is not Interval.DAY


class Bar(BaseModel):
    """A single OHLCV bar for one symbol at one point in time.

    ``timestamp`` should be timezone-aware and is normalised/stored as UTC.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    interval: Interval
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    @model_validator(mode="after")
    def _check_consistency(self) -> Bar:
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if not (self.low <= self.open <= self.high):
            raise ValueError("open must be within [low, high]")
        if not (self.low <= self.close <= self.high):
            raise ValueError("close must be within [low, high]")
        return self


# Column order used for storage I/O. Keep in sync with the store schema.
BAR_COLUMNS: tuple[str, ...] = (
    "symbol",
    "interval",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
