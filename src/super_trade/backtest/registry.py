"""Strategy registry — build a :class:`Strategy` from a name + params.

Mirrors ``metrics.METRICS``: a string key maps to each strategy *family*, so a
run can be described as data (``"sma_cross"`` + ``{"fast": 10, "slow": 30}``)
rather than a live object. That's what lets the ``runner`` layer serialize a run
spec, hash it, and ship it to a worker process or a Ray node.

The key is the family, not the instance ``name`` — ``SmaCross(10, 30).name`` is
``"sma_cross_10_30"`` (params baked in), whereas the registry key is the stable
``"sma_cross"``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .strategies import BuyAndHold, RsiReversion, ScaledRsiReversion, SmaCross
from .strategy import Strategy

# Registry of every strategy family, keyed by a stable name (cf. metrics.METRICS).
STRATEGIES: dict[str, type[Strategy]] = {
    "buy_and_hold": BuyAndHold,
    "sma_cross": SmaCross,
    "rsi_reversion": RsiReversion,
    "scaled_rsi": ScaledRsiReversion,
}


def build_strategy(name: str, params: Mapping[str, Any] | None = None) -> Strategy:
    """Construct the strategy registered under ``name`` with ``params``.

    Args:
        name: A key in :data:`STRATEGIES` (e.g. ``"sma_cross"``).
        params: Keyword arguments for the strategy's constructor. ``None`` uses
            the strategy's own defaults.

    Raises:
        KeyError: If ``name`` is not a registered strategy.
    """
    try:
        cls = STRATEGIES[name]
    except KeyError:
        known = ", ".join(sorted(STRATEGIES))
        raise KeyError(f"unknown strategy {name!r}; registered: {known}") from None
    return cls(**(params or {}))


__all__ = ["STRATEGIES", "build_strategy"]
