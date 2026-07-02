"""Local multi-process runner — saturate one machine's cores.

Each spec's ``EventDrivenBacktest`` is a Python-CPU-bound sequential loop, so the
win comes from running *independent* specs in parallel across processes (sidestepping
the GIL). Uses the stdlib ``ProcessPoolExecutor`` — no third-party dependency.

The spec, the store, and the reduced outcome all pickle, so nothing special is
needed to cross the process boundary; heavy result frames are dropped inside the
worker before the outcome is returned.
"""

from __future__ import annotations

import multiprocessing
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import logfire

from super_trade.data.store import DataStore

from .base import Runner, execute_spec
from .report import RunOutcome, SweepReport
from .spec import RunSpec


class MultiProcessRunner(Runner):
    """Run specs concurrently across local worker processes.

    Args:
        max_workers: Number of worker processes. ``None`` lets the pool default to
            the CPU count.

    Uses the ``spawn`` start method deliberately: a spec's engine imports Polars,
    whose Rayon threadpool does **not** survive ``fork`` (the classic
    fork-after-threads deadlock). ``spawn`` gives each worker a clean interpreter —
    the same isolation Ray provides — at the cost of a slower process start.
    """

    def __init__(self, max_workers: int | None = None) -> None:
        self._max_workers = max_workers

    def run(
        self,
        specs: Iterable[RunSpec],
        store: DataStore,
        *,
        artifacts_dir: str | Path | None = None,
    ) -> SweepReport:
        specs = list(specs)
        ad = str(artifacts_dir) if artifacts_dir is not None else None
        outcomes: list[RunOutcome] = []
        with (
            logfire.span(
                "sweep",
                runner="multiprocess",
                n_specs=len(specs),
                workers=self._max_workers,
            ),
            ProcessPoolExecutor(
                max_workers=self._max_workers,
                mp_context=multiprocessing.get_context("spawn"),
            ) as pool,
        ):
            futures = [pool.submit(execute_spec, spec, store, ad) for spec in specs]
            for future in as_completed(futures):
                outcomes.append(future.result())
        failures = sum(1 for o in outcomes if not o.ok)
        logfire.info(
            "sweep complete: {ok}/{n} ok", ok=len(outcomes) - failures, n=len(outcomes)
        )
        return SweepReport(outcomes)


__all__ = ["MultiProcessRunner"]
