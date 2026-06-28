"""Composable cross-sectional scorers — rank symbols, higher = more preferred.

A :class:`Scorer` turns the feature frame into a score per symbol (a ``pl.Expr``);
the :class:`~super_trade.selection.selector.Selector` sorts by it and takes the best.
Scorers **blend** with ``*`` (weight) and ``+`` (sum), so a preference like "mostly
low institutional ownership, partly recent momentum" is::

    score = 0.7 * Rank("inst_ownership", ascending=True) \
          + 0.3 * Rank("momentum", ascending=False)

Blend on :class:`Rank` (normalised to ``[0, 1]``), not raw features — otherwise a
column measured in billions (市值) would swamp one measured in tenths (a return), and
the weights wouldn't mean what they look like.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import polars as pl


class Scorer(ABC):
    """A per-symbol score over the feature cross-section (higher = preferred).

    Subclasses implement :meth:`score`; instances blend with ``*`` and ``+``.
    """

    @abstractmethod
    def score(self) -> pl.Expr:
        """Return a float ``pl.Expr`` — the preference score per symbol."""

    def __mul__(self, weight: float) -> Scorer:
        return _Weighted(self, weight)

    __rmul__ = __mul__  # allow `0.7 * scorer`

    def __add__(self, other: Scorer) -> Scorer:
        return _Sum(self, other)


class _Weighted(Scorer):
    """``w * scorer`` — scale a score by a blend weight."""

    def __init__(self, inner: Scorer, weight: float) -> None:
        self._inner = inner
        self._weight = weight

    def score(self) -> pl.Expr:
        return self._inner.score() * self._weight


class _Sum(Scorer):
    """``a + b`` — add two scores."""

    def __init__(self, left: Scorer, right: Scorer) -> None:
        self._left = left
        self._right = right

    def score(self) -> pl.Expr:
        return self._left.score() + self._right.score()


class Rank(Scorer):
    """Normalised cross-sectional rank of ``column`` in ``[0, 1]`` (1 = best).

    ``ascending=True`` prefers **low** values (rank 1 to the smallest) — use it for
    "less institutional ownership is better"; ``ascending=False`` prefers high values
    (momentum, liquidity). Normalising to ``[0, 1]`` makes weighted blends comparable
    across features of wildly different scale.
    """

    def __init__(self, column: str, ascending: bool = False) -> None:
        self.column = column
        self.ascending = ascending

    def score(self) -> pl.Expr:
        # Map the *preferred* end to the highest score. ascending=True means low
        # values are preferred, so the smallest value must rank highest → rank with
        # descending=True (largest gets rank 1, smallest gets rank N); /N → (0, 1].
        ranked = pl.col(self.column).rank(method="average", descending=self.ascending)
        return ranked / pl.len()


class Raw(Scorer):
    """Use a feature ``column`` directly as the score (``negate`` to prefer low).

    Handy when the raw value is already a sensible preference (e.g. a precomputed
    alpha column); otherwise prefer :class:`Rank` for blendable, scale-free scores.
    """

    def __init__(self, column: str, negate: bool = False) -> None:
        self.column = column
        self.negate = negate

    def score(self) -> pl.Expr:
        col = pl.col(self.column)
        return -col if self.negate else col
