"""Runner interface + the shared unit of work every backend maps over.

``execute_spec`` is a **module-level, picklable** function so that
``ProcessPoolExecutor`` and Ray can both ship it to a worker. It runs one spec to
completion, reduces the result to ``stats()`` (dropping the heavy ``fills`` /
``positions`` / ``bars`` frames before they cross a process boundary), optionally
persists the equity curve, and captures any exception as a failed ``RunOutcome``.

Backends differ only in *how* they map ``execute_spec`` over the specs — sequentially
(:class:`~super_trade.runner.simple.SimpleRunner`), across local processes
(:class:`~super_trade.runner.multiprocess.MultiProcessRunner`), or across a Ray
cluster (:class:`~super_trade.runner.ray_runner.RayRunner`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

from super_trade.data.store import DataStore

from .report import RunOutcome, SweepReport
from .spec import RunSpec


def execute_spec(
    spec: RunSpec, store: DataStore, artifacts_dir: str | None = None
) -> RunOutcome:
    """Run one spec against ``store`` and reduce it to a :class:`RunOutcome`.

    Never raises: a failing run is returned as an outcome carrying ``error`` so the
    sweep continues (per-run failure isolation).
    """
    key = spec.key()
    try:
        result = spec.build(store).run(start=spec.start, end=spec.end)
        artifact: str | None = None
        if artifacts_dir is not None:
            path = Path(artifacts_dir) / f"{key}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            result.data.write_parquet(path)
            artifact = str(path)
        return RunOutcome(key=key, spec=spec, stats=result.stats(), artifact=artifact)
    except Exception as exc:  # isolate any per-run failure — never abort the sweep
        return RunOutcome(key=key, spec=spec, error=repr(exc))


class Runner(ABC):
    """Fan a collection of :class:`RunSpec` out and collect a :class:`SweepReport`.

    Implementations vary the execution backend; the unit of work (``execute_spec``)
    and the reduction (``stats`` per run) are shared. ``store`` must be picklable so
    workers can reconstruct their own handle — ``ClickHouseStore`` (lazy connection)
    and the test ``FakeStore`` both are.
    """

    @abstractmethod
    def run(
        self,
        specs: Iterable[RunSpec],
        store: DataStore,
        *,
        artifacts_dir: str | Path | None = None,
    ) -> SweepReport:
        """Execute every spec and return the collected outcomes."""


__all__ = ["Runner", "execute_spec"]
