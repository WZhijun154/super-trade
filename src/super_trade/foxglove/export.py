"""Export a backtest to an MCAP log for Foxglove.

Turns a :class:`~super_trade.backtest.result.BacktestResult` (its equity curve plus
the event-driven engine's per-bar ``positions`` and per-trade ``fills``) into an
``.mcap`` file with protobuf-encoded messages on time-correlated topics:

* ``/equity``    — :class:`Equity` per bar (value, cash, drawdown)
* ``/portfolio`` — :class:`Portfolio` per bar (snapshot of all open positions)
* ``/fills``     — :class:`Fill` per executed trade

Open the file in Foxglove and scrub: every topic shares one timeline, so price,
positions, cash and fills move together. The schema is the buf-managed
``supertrade.v1`` package (see the ``foxglove-trade`` repo).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from mcap_protobuf.writer import Writer

from super_trade.backtest.result import BacktestResult

from ._proto.supertrade.v1 import trade_pb2 as pb


def _to_ns(dt: datetime) -> int:
    """Epoch nanoseconds from a datetime (naive values are treated as UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1_000_000_000)


def export_mcap(result: BacktestResult, path: str | Path) -> Path:
    """Write ``result`` to an MCAP file at ``path``; returns the path.

    ``/equity`` is always written. ``/portfolio`` and ``/fills`` are written when
    the result carries ``positions`` / ``fills`` (the event-driven engine fills
    these; the vectorized engine leaves them ``None``).
    """
    path = Path(path)
    # equity + cash per timestamp, plus drawdown (equity / running peak - 1, <= 0).
    eq = result.data.with_columns(
        (pl.col("equity") / pl.col("equity").cum_max() - 1).alias("drawdown")
    )
    eq_by_ts = {row["timestamp"]: row for row in eq.iter_rows(named=True)}

    with path.open("wb") as f, Writer(f) as writer:
        # --- /equity ---
        for row in eq.iter_rows(named=True):
            ns = _to_ns(row["timestamp"])
            msg = pb.Equity(
                equity=row["equity"],
                cash=row.get("cash") or 0.0,  # vectorized frames have no cash column
                drawdown=row["drawdown"],
            )
            msg.time.FromNanoseconds(ns)
            writer.write_message(
                topic="/equity", message=msg, log_time=ns, publish_time=ns
            )

        # --- /portfolio (per-bar position snapshots, grouped by timestamp) ---
        if result.positions is not None and result.positions.height > 0:
            for ts, group in _group_by_ts(result.positions):
                ns = _to_ns(ts)
                head = eq_by_ts.get(ts, {})
                equity = float(head.get("equity", 0.0)) or 0.0
                msg = pb.Portfolio(
                    equity=equity,
                    cash=float(head.get("cash", 0.0)),
                    num_positions=len(group),
                )
                msg.time.FromNanoseconds(ns)
                for p in group:
                    mv = float(p["market_value"])
                    msg.positions.append(
                        pb.Position(
                            symbol=p["symbol"],
                            shares=int(p["shares"]),
                            avg_price=float(p["avg_price"]),
                            price=float(p["price"]),
                            market_value=mv,
                            unrealized_pnl=float(p["unrealized_pnl"]),
                            weight=mv / equity if equity else 0.0,
                        )
                    )
                writer.write_message(
                    topic="/portfolio", message=msg, log_time=ns, publish_time=ns
                )

        # --- /bars (OHLCV, for the candlestick panel) ---
        if result.bars is not None and result.bars.height > 0:
            for row in result.bars.iter_rows(named=True):
                ns = _to_ns(row["timestamp"])
                msg = pb.Bar(
                    symbol=row["symbol"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
                msg.time.FromNanoseconds(ns)
                writer.write_message(
                    topic="/bars", message=msg, log_time=ns, publish_time=ns
                )

        # --- /fills ---
        if result.fills is not None and result.fills.height > 0:
            for row in result.fills.iter_rows(named=True):
                if row["timestamp"] is None:
                    continue
                ns = _to_ns(row["timestamp"])
                msg = pb.Fill(
                    symbol=row["symbol"],
                    side=row["side"],
                    shares=int(row["shares"]),
                    price=float(row["price"]),
                    cost=float(row["cost"]),
                    notional=float(row["notional"]),
                    reason=row["reason"],
                )
                msg.time.FromNanoseconds(ns)
                writer.write_message(
                    topic="/fills", message=msg, log_time=ns, publish_time=ns
                )

    return path


def _group_by_ts(
    positions: pl.DataFrame,
) -> Iterator[tuple[datetime, list[dict[str, Any]]]]:
    """Yield (timestamp, [row dicts]) groups in chronological order."""
    current_ts: datetime | None = None
    bucket: list[dict[str, Any]] = []
    for row in positions.iter_rows(named=True):
        if row["timestamp"] != current_ts:
            if bucket and current_ts is not None:
                yield current_ts, bucket
            current_ts = row["timestamp"]
            bucket = []
        bucket.append(row)
    if bucket and current_ts is not None:
        yield current_ts, bucket
