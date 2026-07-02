"""Single-process runner — the reference backend.

Runs every spec sequentially in the calling process. It's the simplest correct
implementation (and the oracle the parallel backends are tested against), and the
right choice for small sweeps or when a debugger/profiler wants one process.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import logfire

from super_trade.data.store import DataStore

from .base import Runner, execute_spec
from .report import SweepReport
from .spec import RunSpec


class SimpleRunner(Runner):
    """Execute specs one at a time, in-process."""

    def run(
        self,
        specs: Iterable[RunSpec],
        store: DataStore,
        *,
        artifacts_dir: str | Path | None = None,
    ) -> SweepReport:
        specs = list(specs)
        ad = str(artifacts_dir) if artifacts_dir is not None else None
        with logfire.span("sweep", runner="simple", n_specs=len(specs)):
            outcomes = [execute_spec(spec, store, ad) for spec in specs]
        failures = sum(1 for o in outcomes if not o.ok)
        logfire.info(
            "sweep complete: {ok}/{n} ok", ok=len(outcomes) - failures, n=len(outcomes)
        )
        return SweepReport(outcomes)


__all__ = ["SimpleRunner"]
