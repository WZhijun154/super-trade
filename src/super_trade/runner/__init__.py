"""Runner layer — fan many ``EventDrivenBacktest`` runs out at scale.

A *run* is turned into a serializable :class:`RunSpec` (strategy family + params +
universe + window + cost/risk/market config). A :class:`Runner` maps the same picklable
worker over a collection of specs and reduces each to its ``stats()`` in a
:class:`SweepReport` — one comparable row per run, with per-run failure isolation.
This is *to backtesting what ``DailyBackfill`` is to ingest*: a failure-isolated loop
over a work-list that emits a report::

    from super_trade.runner import SimpleRunner, grid

    specs = grid("sma_cross", fast=[5, 10, 20], slow=[30, 60], universe=["600519"])
    report = SimpleRunner().run(specs, store)
    print(report.to_frame().sort("sharpe", descending=True))
    best = report.best("sharpe")

Three backends share one code path, differing only in how they map the work:

* :class:`SimpleRunner` — sequential, in-process (the reference/oracle).
* :class:`MultiProcessRunner` — local ``ProcessPoolExecutor`` (saturate one box).
* :class:`RayRunner` — a Ray cluster on k8s/k3s (optional ``ray`` group).

The runner sits **above** ``EventDrivenBacktest`` and doesn't modify it: each worker
calls ``spec.build(store).run()`` against its own picklable store handle (ClickHouse
reconnects lazily; the test ``FakeStore`` carries its dict), so data is *not* hoisted
into specs — this avoids serializing large frames and lets ClickHouse serve concurrent
reads.

Performance & JIT
-----------------
Scaling here is **across runs, not within a run**. A single ``EventDrivenBacktest`` is
a Python-object-bound loop — it walks ``datetime`` timestamps and ``str`` symbol keys
through nested dicts and mutable dataclasses (``Position``/``Order``/``Fill``), the
numeric per-bar work already reduced to O(1) lookups after a one-time Polars
precompute. That shape is **hostile to a JIT like numba**: the hot path is dict/attr
access and branching (the T+1 ledger, price-limit and suspension rules, per-name risk),
not array math, so ``@njit`` would fall back to object mode and buy nothing.

**Conclusion:** don't add a JIT. Runs are independent and deterministic (no RNG), so the
right lever is fanning them across processes/Ray — which is exactly this layer. *If*
single-run latency ever became the bottleneck, the answer would be a purpose-built
**numeric-kernel engine** (int-encoded symbols, epoch-int timestamps, preallocated numpy
arrays, an ``@njit`` kernel) that trades away market-rule/T+1/risk fidelity — a
separate, deliberate rewrite, not a JIT bolted onto today's loop.
"""

from __future__ import annotations

from .base import Runner, execute_spec
from .multiprocess import MultiProcessRunner
from .ray_runner import RayRunner
from .report import RunOutcome, SweepReport
from .simple import SimpleRunner
from .spec import RunSpec, grid

__all__ = [
    "MultiProcessRunner",
    "RayRunner",
    "RunOutcome",
    "RunSpec",
    "Runner",
    "SimpleRunner",
    "SweepReport",
    "execute_spec",
    "grid",
]
