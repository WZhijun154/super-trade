"""Resample bars to a coarser interval.

1-minute bars are the single source of truth; 5/15/30/60-minute and daily bars are
**derived** from them here. Aggregation is standard OHLCV downsampling
(open=first, high=max, low=min, close=last, volume=sum).

A-share sessions (09:30-11:30 and 13:00-15:00 Beijing) need care: naive wall-clock
windows merge across the lunch break and misalign 60-minute bars (09:30 is not on an
hour grid, and the two sessions can't share one offset). So intraday targets bucket
**per session** — ``bucket = minutes_since_session_open // N`` within each
(symbol, date, session) — which is correct for every interval and never crosses
lunch or a day boundary.
"""

from __future__ import annotations

from datetime import UTC

import polars as pl

from .models import BAR_COLUMNS, Interval

_SHANGHAI = "Asia/Shanghai"
_MORNING_OPEN_MIN = 9 * 60 + 30  # 09:30 -> 570
_AFTERNOON_OPEN_MIN = 13 * 60  # 13:00 -> 780
_LUNCH_SPLIT_MIN = 12 * 60  # noon, divides the two sessions

# Order-independent OHLCV aggregation: open/close are pinned to the chronological
# first/last bar (group_by does not preserve row order), high/low/volume are
# commutative.
_OHLCV_AGG = [
    pl.col("open").sort_by("timestamp").first(),
    pl.col("high").max(),
    pl.col("low").min(),
    pl.col("close").sort_by("timestamp").last(),
    pl.col("volume").sum(),
]


def resample(
    bars: pl.DataFrame,
    target: Interval,
    *,
    source: Interval = Interval.MINUTE,
) -> pl.DataFrame:
    """Aggregate ``bars`` (at ``source`` interval) up to ``target``.

    Returns bars in ``BAR_COLUMNS`` order with ``interval = target``. ``target`` must
    be strictly coarser than ``source``; an equal interval returns a sorted copy.
    """
    if target.minutes < source.minutes:
        raise ValueError(f"cannot resample {source.value} up to a finer {target.value}")
    if bars.height == 0 or target == source:
        return bars.sort("symbol", "timestamp")

    if target is Interval.DAY:
        out = _resample_daily(bars)
    else:
        out = _resample_intraday(bars, target.minutes)

    return (
        out.with_columns(pl.lit(target.value).alias("interval"))
        .select(BAR_COLUMNS)
        .sort("symbol", "timestamp")
    )


def _resample_intraday(bars: pl.DataFrame, every: int) -> pl.DataFrame:
    """Per-session bucketing — correct across the lunch break for all intervals."""
    bj = pl.col("timestamp").dt.convert_time_zone(_SHANGHAI)
    # Cast hour to a wide int first — dt.hour()/dt.minute() are i8 and 9*60 overflows.
    minutes_in_day = bj.dt.hour().cast(pl.Int32) * 60 + bj.dt.minute()
    session_open = (
        pl.when(minutes_in_day < _LUNCH_SPLIT_MIN)
        .then(_MORNING_OPEN_MIN)
        .otherwise(_AFTERNOON_OPEN_MIN)
    )
    return (
        bars.with_columns(
            bj.dt.date().alias("_date"),
            session_open.alias("_session"),
            ((minutes_in_day - session_open) // every).alias("_bucket"),
        )
        .group_by("symbol", "_date", "_session", "_bucket")
        .agg(pl.col("timestamp").min(), *_OHLCV_AGG)
    )


def _resample_daily(bars: pl.DataFrame) -> pl.DataFrame:
    """One bar per Beijing trading date, timestamped at UTC midnight."""
    return (
        bars.with_columns(
            pl.col("timestamp").dt.convert_time_zone(_SHANGHAI).dt.date().alias("_date")
        )
        .group_by("symbol", "_date")
        .agg(*_OHLCV_AGG)
        .with_columns(
            pl.col("_date")
            .cast(pl.Datetime("ms"))
            .dt.replace_time_zone(str(UTC))
            .alias("timestamp")
        )
    )
