"""Sweep results — one reduced row per run, with per-run failure isolation.

Each run is reduced to its :meth:`~super_trade.backtest.result.BacktestResult.stats`
plus the spec that produced it (heavy frames are dropped in the worker). A failed
run is captured as a :class:`RunOutcome` with an ``error`` instead of aborting the
sweep — the same failure-isolation contract as ``ingest.BackfillReport``.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from .spec import RunSpec


@dataclass(frozen=True)
class RunOutcome:
    """The result of a single spec: stats on success, an error string on failure."""

    key: str
    spec: RunSpec
    stats: dict[str, float] | None = None
    error: str | None = None
    artifact: str | None = None  # path to persisted equity frame, if any

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class SweepReport:
    """All outcomes of a runner's fan-out, plus reductions over them."""

    outcomes: list[RunOutcome]

    @property
    def failures(self) -> list[RunOutcome]:
        return [o for o in self.outcomes if not o.ok]

    def to_frame(self) -> pl.DataFrame:
        """One row per run: key, strategy, params, error, and every stat column.

        Params are flattened to ``param_<name>`` columns; stats to their own columns
        (``sharpe``, ``cagr`` …). Failed runs have null stats.
        """
        rows: list[dict[str, object]] = []
        for o in self.outcomes:
            row: dict[str, object] = {
                "key": o.key,
                "strategy": o.spec.strategy,
                "label": o.spec.label,
            }
            for name, value in o.spec.params.items():
                row[f"param_{name}"] = value
            row["error"] = o.error
            if o.stats is not None:
                row.update(o.stats)
            rows.append(row)
        return pl.DataFrame(rows)

    def best(
        self, metric: str = "sharpe", *, maximize: bool = True
    ) -> RunOutcome | None:
        """The successful outcome with the best ``metric`` (``None`` if all failed)."""
        scored = [o for o in self.outcomes if o.stats is not None and metric in o.stats]
        if not scored:
            return None
        return (max if maximize else min)(scored, key=lambda o: o.stats[metric])  # type: ignore[index]


__all__ = ["RunOutcome", "SweepReport"]
