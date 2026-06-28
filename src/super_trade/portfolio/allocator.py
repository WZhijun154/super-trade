"""Portfolio allocation — decide *how much* of each selected name to hold.

An :class:`Allocator` turns a feature cross-section (the selected names) into target
**weights** — a ``{symbol: fraction-of-equity}`` dict that sums to at most ``gross``
and never exceeds ``max_weight`` on any one name. Those weights are the portfolio
*budget* per name; the strategy's signal then decides the *timing* within it (the
event-driven engine multiplies the two — see ``EventDrivenBacktest(weights=…)``).

Guidance for a new quant: **start with** :class:`EqualWeight`, **graduate to**
:class:`InverseVol` (size by 1/volatility so one wild small-cap can't dominate risk).
Both are robust and need no return forecast. Skip mean-variance optimisation early —
its estimation error usually costs more than it gains. Allocation is the *smaller*
lever; selection and risk control matter more.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import polars as pl


def _normalise(
    raw: dict[str, float], gross: float, max_weight: float
) -> dict[str, float]:
    """Scale raw (relative) weights to sum to ``gross``, then cap each at the max.

    Normalise *first* so the per-name cap is applied on the final fractions, not on
    the arbitrary raw scale (``1/vol``, a score, …). When a cap binds the total ends
    up under ``gross`` — intentional: we never *force* leverage up to the budget, we
    only ensure we don't exceed it.
    """
    positive = {s: w for s, w in raw.items() if w > 0}
    total = sum(positive.values())
    if total <= 0:
        return {}
    return {s: min(w / total * gross, max_weight) for s, w in positive.items()}


class Allocator(ABC):
    """Map a feature frame (the chosen names) to target weights.

    Args:
        gross: Maximum total invested fraction across the book (cash buffer = 1-gross).
        max_weight: Per-name cap on the weight (concentration limit).
    """

    def __init__(self, *, gross: float = 0.95, max_weight: float = 0.20) -> None:
        self.gross = gross
        self.max_weight = max_weight

    @abstractmethod
    def _raw_weights(self, features: pl.DataFrame) -> dict[str, float]:
        """Unnormalised per-symbol weights (relative sizes); 0 / negative dropped."""

    def weights(self, features: pl.DataFrame) -> dict[str, float]:
        """Return normalised ``{symbol: weight}`` (sum ≤ gross, each ≤ max_weight)."""
        if features.height == 0:
            return {}
        return _normalise(self._raw_weights(features), self.gross, self.max_weight)


class EqualWeight(Allocator):
    """Same weight on every name — the robust, hard-to-beat default (1/N → gross)."""

    def _raw_weights(self, features: pl.DataFrame) -> dict[str, float]:
        return {s: 1.0 for s in features["symbol"].to_list()}


class InverseVol(Allocator):
    """Weight ∝ ``1 / volatility`` — each name contributes similar risk.

    Quieter names get more capital, volatile ones less, so a single jumpy small-cap
    can't dominate the portfolio's risk. Needs a ``vol_col`` in the features
    (``build_features`` provides ``volatility``); non-positive/null vols are skipped.
    """

    def __init__(
        self,
        *,
        vol_col: str = "volatility",
        gross: float = 0.95,
        max_weight: float = 0.20,
    ) -> None:
        super().__init__(gross=gross, max_weight=max_weight)
        self.vol_col = vol_col

    def _raw_weights(self, features: pl.DataFrame) -> dict[str, float]:
        out: dict[str, float] = {}
        for row in features.select("symbol", self.vol_col).iter_rows():
            symbol, vol = row
            if vol is not None and vol > 0:
                out[symbol] = 1.0 / vol
        return out


class ScoreProportional(Allocator):
    """Weight ∝ a (non-negative) score column — more conviction, more capital."""

    def __init__(
        self, score_col: str, *, gross: float = 0.95, max_weight: float = 0.20
    ) -> None:
        super().__init__(gross=gross, max_weight=max_weight)
        self.score_col = score_col

    def _raw_weights(self, features: pl.DataFrame) -> dict[str, float]:
        out: dict[str, float] = {}
        for row in features.select("symbol", self.score_col).iter_rows():
            symbol, score = row
            if score is not None and score > 0:
                out[symbol] = float(score)
        return out
