"""Selector — turn a feature cross-section into a chosen universe (``list[str]``).

A :class:`Selector` is the pipeline: **filter** the cross-section (all filters AND'd),
optionally **rank** the survivors by a blended score, and take the **top N**. Its
output is a plain ``list[str]`` of symbols — exactly what ``EventDrivenBacktest`` /
``ExecutionEngine`` accept as ``universe=``, so selection drops in with no engine
change.

The "method" (retail-pond, momentum, low-vol, …) is entirely expressed by *which*
filters and scorer you pass — the Selector itself is method-agnostic.
"""

from __future__ import annotations

import polars as pl

from .filters import Filter
from .scorers import Scorer

_SCORE_COL = "_score"


class Selector:
    """Filter → rank → top-N over a feature frame.

    Args:
        filters: Predicates a symbol must *all* satisfy (combined with AND). Empty =
            keep everything. Compose richer logic inside one filter with ``& | ~``.
        score: Optional ranking; survivors are sorted by it descending (higher =
            better). ``None`` keeps the post-filter order.
        top_n: Keep at most this many. ``None`` keeps all survivors.
    """

    def __init__(
        self,
        *,
        filters: list[Filter] | None = None,
        score: Scorer | None = None,
        top_n: int | None = None,
    ) -> None:
        self._filters = filters or []
        self._score = score
        self._top_n = top_n

    def select(self, features: pl.DataFrame) -> list[str]:
        """Return the chosen symbols, best first when a score is given."""
        if features.height == 0:
            return []
        df = features

        # 1) AND every filter mask; a null comparison drops the symbol (fill_null).
        if self._filters:
            mask = pl.lit(True)
            for f in self._filters:
                mask = mask & f.mask()
            df = df.filter(mask.fill_null(False))

        # 2) Rank survivors by the blended score (highest first).
        if self._score is not None:
            df = df.with_columns(self._score.score().alias(_SCORE_COL)).sort(
                _SCORE_COL, descending=True, nulls_last=True
            )

        # 3) Keep the top N.
        if self._top_n is not None:
            df = df.head(self._top_n)

        return df["symbol"].to_list()
