"""``RunSpec`` — one event-driven backtest described as data.

A spec is a frozen, serializable value: it captures every ``EventDrivenBacktest``
knob (strategy family + params, universe, window, cost/risk/market config) without
holding a live engine or store. That's what lets a :class:`~super_trade.runner`
fan a sweep out to worker processes or Ray nodes — each worker reconstructs the
engine from the spec via :meth:`RunSpec.build` and reads from its own store handle.

``key()`` is a stable content hash (of the canonical JSON form) usable as a cache
key or artifact filename. The config objects it references (``CostModel``,
``RiskLimits``, ``MarketRules``) are all frozen dataclasses, so specs pickle cleanly.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from super_trade.backtest.costs import CostModel
from super_trade.backtest.registry import build_strategy
from super_trade.data import Interval
from super_trade.execution import (
    EventDrivenBacktest,
    MarketRules,
    RiskLimits,
    RiskManager,
)

if TYPE_CHECKING:
    from super_trade.data.store import DataStore


def _canonical(obj: Any) -> Any:
    """Convert a spec field into a JSON-serializable, order-stable form."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _canonical(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Mapping):
        return {k: _canonical(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_canonical(v) for v in obj]
    return obj


@dataclass(frozen=True)
class RunSpec:
    """A single event-driven backtest, as a serializable value.

    Every field mirrors an ``EventDrivenBacktest`` argument. ``risk`` stores the
    immutable :class:`RiskLimits` (not a live ``RiskManager``, which carries mutable
    intraday state) — :meth:`build` wraps it fresh per run.
    """

    strategy: str
    params: Mapping[str, Any] = field(default_factory=dict)
    universe: tuple[str, ...] | None = None
    cash: float = 1_000_000.0
    interval: Interval = Interval.DAY
    resample_from: Interval | None = None
    start: datetime | None = None
    end: datetime | None = None
    costs: CostModel | None = None
    risk: RiskLimits | None = None
    rules: MarketRules | None = None
    weights: Mapping[str, float] | None = None
    label: str | None = None

    def key(self) -> str:
        """Stable 12-char content hash — same spec always yields the same key."""
        payload = json.dumps(_canonical(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(payload.encode()).hexdigest()[:12]

    def build(self, store: DataStore) -> EventDrivenBacktest:
        """Reconstruct the configured engine against ``store``.

        ``start``/``end`` are *not* set here — they are run-time arguments to
        ``EventDrivenBacktest.run()``, applied by the runner's worker.
        """
        return EventDrivenBacktest(
            store,
            build_strategy(self.strategy, self.params),
            cash=self.cash,
            costs=self.costs,
            risk=RiskManager(self.risk) if self.risk is not None else None,
            universe=list(self.universe) if self.universe is not None else None,
            interval=self.interval,
            resample_from=self.resample_from,
            rules=self.rules,
            weights=dict(self.weights) if self.weights is not None else None,
        )


def grid(
    strategy: str,
    *,
    universe: Sequence[str] | None = None,
    cash: float = 1_000_000.0,
    interval: Interval = Interval.DAY,
    resample_from: Interval | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    costs: CostModel | None = None,
    risk: RiskLimits | None = None,
    rules: MarketRules | None = None,
    weights: Mapping[str, float] | None = None,
    **param_grid: Sequence[Any],
) -> list[RunSpec]:
    """Cartesian product of strategy params → one :class:`RunSpec` per combination.

    Reserved keyword args (``universe``, ``cash``, ``interval`` …) are held constant
    across the sweep; every *other* keyword is a strategy-parameter axis whose value
    is the list of values to sweep::

        grid("sma_cross", fast=[5, 10, 20], slow=[30, 60], universe=["600519"])
        # → 6 specs, one per (fast, slow) pair

    An empty ``param_grid`` yields a single spec using the strategy's defaults.
    """
    axes = list(param_grid.items())
    combos = itertools.product(*(values for _, values in axes)) if axes else [()]
    uni = tuple(universe) if universe is not None else None
    return [
        RunSpec(
            strategy=strategy,
            params={name: value for (name, _), value in zip(axes, combo, strict=True)},
            universe=uni,
            cash=cash,
            interval=interval,
            resample_from=resample_from,
            start=start,
            end=end,
            costs=costs,
            risk=risk,
            rules=rules,
            weights=weights,
        )
        for combo in combos
    ]


__all__ = ["RunSpec", "grid"]
