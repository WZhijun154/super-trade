"""Portfolio allocation — size the selected names against each other.

Given the feature cross-section of the chosen universe, an :class:`Allocator`
produces target weights (``{symbol: fraction-of-equity}``, summing to ≤ ``gross``,
each ≤ ``max_weight``). Feed them to the engine as the per-name budget::

    from super_trade.selection import build_features
    from super_trade.portfolio import InverseVol

    feats = build_features(store, symbols=universe)
    weights = InverseVol(gross=0.9, max_weight=0.2).weights(feats)
    EventDrivenBacktest(store, strategy, universe=universe, weights=weights).run()

The engine treats the strategy signal as *timing* and the allocation as *budget*
(final target = signal * weight). Start with :class:`EqualWeight`, graduate to
:class:`InverseVol`.
"""

from __future__ import annotations

from .allocator import Allocator, EqualWeight, InverseVol, ScoreProportional
from .rebalance import periodic_schedule

__all__ = [
    "Allocator",
    "EqualWeight",
    "InverseVol",
    "ScoreProportional",
    "periodic_schedule",
]
