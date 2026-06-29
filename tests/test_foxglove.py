"""Tests for the Foxglove MCAP exporter (round-trips through the mcap reader)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
from factories import make_bars
from fakes import FakeStore
from mcap_protobuf.reader import read_protobuf_messages

from super_trade.backtest import BuyAndHold, VectorizedEngine
from super_trade.data import Interval
from super_trade.execution import EventDrivenBacktest, RiskLimits, RiskManager
from super_trade.foxglove import export_mcap


def _topic_counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for m in read_protobuf_messages(str(path)):
        counts[m.topic] = counts.get(m.topic, 0) + 1
    return counts


def test_event_driven_export_has_all_topics(tmp_path: Path) -> None:
    store = FakeStore()
    store.write_bars(make_bars("AAA", interval=Interval.DAY, count=80))
    result = EventDrivenBacktest(
        store,
        BuyAndHold(),
        cash=1_000_000,
        universe=["AAA"],
        risk=RiskManager(RiskLimits(stop_loss=0.08)),
    ).run()

    out = export_mcap(result, tmp_path / "run.mcap")
    assert out.exists() and out.stat().st_size > 0

    counts = _topic_counts(out)
    # one Equity per bar; Bar/Portfolio/Fill present once the strategy is invested
    assert counts["/equity"] == result.data.height
    assert counts["/bars"] == result.bars.height
    assert counts["/portfolio"] == result.positions.height
    assert counts["/fills"] == result.fills.height


def test_vectorized_export_is_equity_only(tmp_path: Path) -> None:
    # The vectorized engine leaves fills/positions None → only /equity is written.
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = pl.DataFrame(
        {
            "timestamp": [start + timedelta(days=i) for i in range(30)],
            "close": [100.0 + i for i in range(30)],
        }
    )
    result = VectorizedEngine().run(bars, BuyAndHold())
    assert result.fills is None and result.positions is None

    counts = _topic_counts(export_mcap(result, tmp_path / "v.mcap"))
    assert counts["/equity"] == result.data.height
    assert "/fills" not in counts and "/portfolio" not in counts
