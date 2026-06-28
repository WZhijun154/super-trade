"""Convenience readers that derive any interval from a stored base granularity.

The platform stores **1-minute** bars as the source of truth; coarser intervals are
produced by resampling. ``load_bars`` is the one call that ties read + resample
together so callers (backtests, dashboard, examples) can ask for any interval.
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from .models import Interval
from .resample import resample
from .store import DataStore


def load_bars(
    store: DataStore,
    symbol: str,
    interval: Interval,
    start: datetime | None = None,
    end: datetime | None = None,
    *,
    resample_from: Interval | None = None,
) -> pl.DataFrame:
    """Return bars for ``symbol`` at ``interval``.

    With ``resample_from`` set (e.g. ``Interval.MINUTE``), the base bars are read and
    **resampled** to ``interval`` — the "system on 1-minute data" path. Without it,
    the ``interval`` series is read directly (unchanged behaviour).
    """
    if resample_from is None or resample_from == interval:
        return store.read_bars(symbol, interval, start, end)
    base = store.read_bars(symbol, resample_from, start, end)
    return resample(base, interval, source=resample_from)
