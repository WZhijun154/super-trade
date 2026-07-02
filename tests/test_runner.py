"""Tests for the runner layer — specs, the report, and the three backends.

All against a picklable ``FakeStore`` (unit tier, no services). The Ray backend is
skipped unless the optional ``ray`` group is installed.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from fakes import FakeStore

from super_trade.backtest.result import BacktestResult
from super_trade.data import Bar, Interval
from super_trade.runner import (
    MultiProcessRunner,
    RunSpec,
    SimpleRunner,
    SweepReport,
    grid,
)

SYMBOL = "AAA"


def _wave_store(symbol: str = SYMBOL, n: int = 90) -> FakeStore:
    """`n` daily bars on a gentle sine wave — enough crossings for SMA strategies."""
    store = FakeStore()
    start = datetime(2024, 1, 1, tzinfo=UTC)
    store.write_bars(
        [
            Bar(
                symbol=symbol,
                interval=Interval.DAY,
                timestamp=start + timedelta(days=i),
                open=(c := 100.0 + 10.0 * math.sin(i / 5.0)),
                high=c + 1.0,
                low=c - 1.0,
                close=c,
                volume=10_000_000,
            )
            for i in range(n)
        ]
    )
    return store


# --- specs ----------------------------------------------------------------


def test_grid_is_cartesian_product() -> None:
    specs = grid("sma_cross", fast=[5, 10, 20], slow=[30, 60], universe=[SYMBOL])
    assert len(specs) == 6
    combos = {(s.params["fast"], s.params["slow"]) for s in specs}
    assert combos == {(5, 30), (5, 60), (10, 30), (10, 60), (20, 30), (20, 60)}
    assert all(s.universe == (SYMBOL,) for s in specs)


def test_grid_empty_uses_defaults() -> None:
    specs = grid("buy_and_hold", universe=[SYMBOL])
    assert len(specs) == 1 and specs[0].params == {}


def test_key_is_stable_and_param_sensitive() -> None:
    a = RunSpec("sma_cross", {"fast": 5, "slow": 20})
    b = RunSpec("sma_cross", {"fast": 5, "slow": 20})
    c = RunSpec("sma_cross", {"fast": 6, "slow": 20})
    assert a.key() == b.key()
    assert a.key() != c.key()


def test_spec_build_runs() -> None:
    store = _wave_store()
    spec = RunSpec("sma_cross", {"fast": 5, "slow": 20}, universe=(SYMBOL,))
    result = spec.build(store).run()
    assert isinstance(result, BacktestResult)
    assert result.data.height > 0


# --- SimpleRunner ---------------------------------------------------------


def test_simple_runner_sweep() -> None:
    store = _wave_store()
    specs = grid("sma_cross", fast=[5, 10], slow=[20, 40], universe=[SYMBOL])
    report = SimpleRunner().run(specs, store)

    assert isinstance(report, SweepReport)
    frame = report.to_frame()
    assert frame.height == len(specs)
    assert {"key", "param_fast", "param_slow", "sharpe"} <= set(frame.columns)
    assert not report.failures

    best = report.best("sharpe")
    assert best is not None and best.ok


def test_failure_is_isolated_per_spec() -> None:
    store = _wave_store()
    good = grid("sma_cross", fast=[5], slow=[20], universe=[SYMBOL])
    broken = RunSpec("no_such_strategy", universe=(SYMBOL,))
    report = SimpleRunner().run([*good, broken], store)

    assert len(report.outcomes) == 2
    assert len(report.failures) == 1
    (failure,) = report.failures
    assert failure.spec.strategy == "no_such_strategy"
    assert failure.stats is None and failure.error is not None
    # the good run still succeeded
    assert any(o.ok for o in report.outcomes)


# --- MultiProcessRunner ---------------------------------------------------


def test_multiprocess_matches_simple() -> None:
    store = _wave_store()
    specs = grid("sma_cross", fast=[5, 10], slow=[20, 40], universe=[SYMBOL])

    simple = {o.key: o.stats for o in SimpleRunner().run(specs, store).outcomes}
    multi = {
        o.key: o.stats
        for o in MultiProcessRunner(max_workers=2).run(specs, store).outcomes
    }

    assert simple.keys() == multi.keys()
    for key, stats in simple.items():
        assert stats is not None and multi[key] is not None
        assert stats == pytest.approx(multi[key], rel=1e-9, nan_ok=True)


# --- RayRunner (skipped unless the `ray` group is installed) ---------------


def test_ray_runner_matches_simple() -> None:
    pytest.importorskip("ray")
    from super_trade.runner import RayRunner

    store = _wave_store()
    specs = grid("sma_cross", fast=[5, 10], slow=[20, 40], universe=[SYMBOL])

    simple = {o.key: o.stats for o in SimpleRunner().run(specs, store).outcomes}
    rayed = {o.key: o.stats for o in RayRunner().run(specs, store).outcomes}

    assert simple.keys() == rayed.keys()
    for key, stats in simple.items():
        assert stats is not None and rayed[key] is not None
        assert stats == pytest.approx(rayed[key], rel=1e-9, nan_ok=True)
