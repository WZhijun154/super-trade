"""Composable cross-sectional filters — boolean predicates over the feature frame.

A :class:`Filter` answers, for each symbol, "does it pass?" as a boolean ``pl.Expr``
over the feature columns. Filters **combine** with ``&`` (and), ``|`` (or), ``~``
(not), so a screening rule is built up from small, reusable pieces rather than one
bespoke function. The "retail-pond" universe, for instance, is just::

    small  = Range("float_mktcap", high=10e9)      # small float cap
    liquid = Range("adv", low=5e6, high=1e8)        # tradeable, but not quant-sized
    quiet  = AtMost("inst_ownership", 0.20)         # low institutional ownership
    clean  = ~Flag("is_st")                          # exclude ST / *ST
    pond   = small & liquid & quiet & clean

A null feature (e.g. a symbol missing from the fundamentals join) fails numeric
comparisons, so such names are excluded unless a filter opts to keep them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import polars as pl


class Filter(ABC):
    """A boolean predicate over the feature cross-section.

    Subclasses implement :meth:`mask`; instances compose with ``&``, ``|``, ``~``.
    """

    @abstractmethod
    def mask(self) -> pl.Expr:
        """Return a boolean ``pl.Expr`` — True for symbols that pass."""

    def __and__(self, other: Filter) -> Filter:
        return _BinaryFilter(self, other, "and")

    def __or__(self, other: Filter) -> Filter:
        return _BinaryFilter(self, other, "or")

    def __invert__(self) -> Filter:
        return _NotFilter(self)


class _BinaryFilter(Filter):
    """``a & b`` / ``a | b`` — combine two filters' masks."""

    def __init__(self, left: Filter, right: Filter, op: str) -> None:
        self._left = left
        self._right = right
        self._op = op

    def mask(self) -> pl.Expr:
        left, right = self._left.mask(), self._right.mask()
        return left & right if self._op == "and" else left | right


class _NotFilter(Filter):
    """``~f`` — negate a filter (null stays excluded, not flipped to True)."""

    def __init__(self, inner: Filter) -> None:
        self._inner = inner

    def mask(self) -> pl.Expr:
        # fill_null(False) so a null never becomes True under negation.
        return ~self._inner.mask().fill_null(False)


class Range(Filter):
    """Keep symbols whose ``column`` is within ``[low, high]`` (inclusive).

    Either bound may be ``None`` (open on that side). The workhorse for band filters
    — market-cap bands, liquidity bands, price floors.
    """

    def __init__(
        self, column: str, low: float | None = None, high: float | None = None
    ) -> None:
        self.column = column
        self.low = low
        self.high = high

    def mask(self) -> pl.Expr:
        col = pl.col(self.column)
        expr = pl.lit(True)
        if self.low is not None:
            expr = expr & (col >= self.low)
        if self.high is not None:
            expr = expr & (col <= self.high)
        return expr


class AtLeast(Filter):
    """Keep symbols with ``column >= value`` (e.g. a liquidity floor)."""

    def __init__(self, column: str, value: float) -> None:
        self.column = column
        self.value = value

    def mask(self) -> pl.Expr:
        return pl.col(self.column) >= self.value


class AtMost(Filter):
    """Keep symbols with ``column <= value`` (e.g. low institutional ownership)."""

    def __init__(self, column: str, value: float) -> None:
        self.column = column
        self.value = value

    def mask(self) -> pl.Expr:
        return pl.col(self.column) <= self.value


class Flag(Filter):
    """Keep symbols whose boolean ``column`` equals ``equals`` (default ``True``).

    Use ``~Flag("is_st")`` to drop ST names, or ``Flag("is_index_member")`` to keep
    only index constituents.
    """

    def __init__(self, column: str, equals: bool = True) -> None:
        self.column = column
        self.equals = equals

    def mask(self) -> pl.Expr:
        return pl.col(self.column) == self.equals
