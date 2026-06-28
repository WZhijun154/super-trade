"""Cross-sectional feature snapshot — one row per symbol, for stock selection.

Selection works on a *cross-section*: a table with one row per candidate symbol and
columns of comparable features, all measured **as of one moment**.
:func:`build_features` assembles that table from the store (OHLCV-derived, real, via
``metrics``) and optionally left-joins a caller-supplied ``fundamentals`` frame
(流通市值 / 机构持股 / ST flag / index membership — assumed available; the ingestion
that fills it is future work).

The result is a plain Polars DataFrame, which the :mod:`~super_trade.selection.filters`
and :mod:`~super_trade.selection.scorers` operate on. Keeping it a DataFrame (not a
bespoke type) is deliberate — features compose with Polars and new columns just
appear, no schema to migrate.
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from super_trade import metrics as m
from super_trade.data import DataStore, Interval

# OHLCV-derived feature columns always produced by build_features().
OHLCV_FEATURES: tuple[str, ...] = (
    "symbol",
    "price",
    "adv",
    "volatility",
    "momentum",
    "bars",
)


def build_features(
    store: DataStore,
    symbols: list[str] | None = None,
    *,
    interval: Interval = Interval.DAY,
    asof: datetime | None = None,
    lookback: int = 60,
    fundamentals: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Build a one-row-per-symbol feature cross-section from the store.

    For each symbol it reads bars up to ``asof`` (causal — never uses the future),
    keeps the last ``lookback`` of them, and computes:

    * ``price`` — last close.
    * ``adv`` — average daily 成交额 (mean of ``close * volume``): the liquidity /
      "how much quant capital can fit" proxy. Low ``adv`` ~ illiquid ~ retail turf.
    * ``volatility`` — annualised volatility (``metrics.annualized_volatility``).
    * ``momentum`` — total return over the window (``metrics.total_return``).
    * ``bars`` — number of bars seen (a listing-age / data-coverage proxy).

    Args:
        store: Source of real OHLCV bars.
        symbols: Candidates; ``None`` means every symbol in the store at ``interval``.
        interval: Bar interval to measure on (daily by default).
        asof: Only use bars at/ before this instant. ``None`` = all available.
        lookback: How many trailing bars the features are computed over.
        fundamentals: Optional per-symbol frame (must have a ``symbol`` column) of
            extra features — e.g. ``float_mktcap``, ``inst_ownership``, ``is_st``,
            ``is_index_member`` — left-joined on ``symbol``. Symbols missing there
            get nulls (filters can exclude them).

    Returns:
        DataFrame with :data:`OHLCV_FEATURES` columns plus any fundamental columns.
        Symbols with no bars in the window are dropped.
    """
    if symbols is None:
        symbols = store.list_symbols(interval)

    rows: list[pl.DataFrame] = []
    for symbol in symbols:
        bars = store.read_bars(symbol, interval, end=asof)
        if bars.height == 0:
            continue  # no data in window → not a candidate
        window = bars.sort("timestamp").tail(lookback)
        rows.append(
            window.select(
                pl.lit(symbol).alias("symbol"),
                pl.col("close").last().alias("price"),
                (pl.col("close") * pl.col("volume")).mean().alias("adv"),
                m.annualized_volatility("close").alias("volatility"),
                m.total_return("close").alias("momentum"),
                pl.len().alias("bars"),
            )
        )

    if not rows:
        # Empty cross-section, but with the right columns so downstream code is happy.
        return pl.DataFrame(
            schema={c: pl.Float64 for c in OHLCV_FEATURES}
        ).with_columns(pl.col("symbol").cast(pl.String), pl.col("bars").cast(pl.UInt32))

    features = pl.concat(rows)
    if fundamentals is not None and fundamentals.height > 0:
        features = features.join(fundamentals, on="symbol", how="left")
    return features
