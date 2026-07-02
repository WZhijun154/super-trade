"""Distributed runner — fan a sweep across a Ray cluster (k8s/k3s via KubeRay).

For sweeps too large for one machine. Ray is an **optional** dependency (the ``ray``
group: ``uv sync --group ray``); the import is deferred so the rest of ``runner``
works without it. The store is ``ray.put`` once and shared by reference; each task
runs the same ``execute_spec`` worker as the local backends, so results are identical.

Point it at a cluster with ``address="auto"`` (inside a Ray pod) or an explicit
``ray://head:10001``; the default starts a local Ray. The container image for
KubeRay is built from ``docker/Dockerfile.ray`` — note that ClickHouse must be
reachable from the worker pods, since each task reads bars from the store itself.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import logfire

from super_trade.data.store import DataStore

from .base import Runner, execute_spec
from .report import RunOutcome, SweepReport
from .spec import RunSpec


def _import_ray() -> Any:
    try:
        import ray
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised only w/o ray
        raise RuntimeError(
            "RayRunner needs the optional 'ray' dependency group. "
            "Install it with: uv sync --group ray"
        ) from exc
    return ray


class RayRunner(Runner):
    """Run specs as Ray tasks across a (local or remote) Ray cluster.

    Args:
        address: Ray cluster address. ``None`` starts/attaches to a local Ray;
            ``"auto"`` attaches to the cluster of the current node (KubeRay pods);
            ``"ray://host:10001"`` connects to a remote head via Ray Client.
        num_cpus: Optional per-task CPU request passed to ``ray.remote``.
        init_kwargs: Extra keyword args forwarded to ``ray.init``.
    """

    def __init__(
        self,
        address: str | None = None,
        *,
        num_cpus: float | None = None,
        init_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._address = address
        self._num_cpus = num_cpus
        self._init_kwargs = init_kwargs or {}

    def run(
        self,
        specs: Iterable[RunSpec],
        store: DataStore,
        *,
        artifacts_dir: str | Path | None = None,
    ) -> SweepReport:
        ray = _import_ray()
        specs = list(specs)
        ad = str(artifacts_dir) if artifacts_dir is not None else None

        if not ray.is_initialized():
            ray.init(address=self._address, **self._init_kwargs)

        remote = ray.remote(execute_spec)
        if self._num_cpus is not None:
            remote = remote.options(num_cpus=self._num_cpus)

        with logfire.span("sweep", runner="ray", n_specs=len(specs)):
            store_ref = ray.put(store)  # ship the store once, share by reference
            futures = [remote.remote(spec, store_ref, ad) for spec in specs]
            outcomes: list[RunOutcome] = ray.get(futures)

        failures = sum(1 for o in outcomes if not o.ok)
        logfire.info(
            "sweep complete: {ok}/{n} ok", ok=len(outcomes) - failures, n=len(outcomes)
        )
        return SweepReport(outcomes)


__all__ = ["RayRunner"]
