"""Stock selection — choose *which* names to trade (the universe).

A cross-sectional layer above the per-symbol strategy: build a feature snapshot
(one row per symbol), then **filter** and **rank** it down to a universe. Everything
is composable — a screening "method" is just a combination of filters and scorers,
not a bespoke function::

    from super_trade.selection import (
        build_features, Selector, Range, AtMost, Flag, Rank,
    )

    feats = build_features(store, fundamentals=fundamentals)   # cross-section
    pond = Selector(
        filters=[
            Range("float_mktcap", high=10e9),   # small float cap
            Range("adv", low=5e6, high=1e8),     # tradeable, not quant-sized
            AtMost("inst_ownership", 0.20),      # low institutional ownership
            ~Flag("is_st"),                       # drop ST / *ST
        ],
        score=Rank("inst_ownership", ascending=True)
        + Rank("momentum", ascending=False),
        top_n=20,
    )
    universe = pond.select(feats)   # list[str] -> EventDrivenBacktest(universe=…)

The retail-pond example above harvests 散户-dominated corners; swap the filters/scorer
for any other method. Selection output feeds ``universe=`` unchanged.

Note: OHLCV-derived features (``adv``, ``volatility``, ``momentum``) are computed from
real bars; fundamental columns (``float_mktcap``, ``inst_ownership``, ``is_st`` …) are
joined from a caller-supplied ``fundamentals`` frame — the ingestion that fills it is
future work.
"""

from __future__ import annotations

from .features import OHLCV_FEATURES, build_features
from .filters import AtLeast, AtMost, Filter, Flag, Range
from .scorers import Rank, Raw, Scorer
from .selector import Selector

__all__ = [
    "OHLCV_FEATURES",
    "AtLeast",
    "AtMost",
    "Filter",
    "Flag",
    "Range",
    "Rank",
    "Raw",
    "Scorer",
    "Selector",
    "build_features",
]
