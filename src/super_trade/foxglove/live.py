"""Live Foxglove WebSocket bridge — stream telemetry to a connected Foxglove.

Same ``supertrade.v1`` schemas as the MCAP exporter, but pushed over the Foxglove
WebSocket protocol so the Trade Cockpit panel updates **live** (open Foxglove ->
"Open connection" -> Foxglove WebSocket -> ``ws://host:port``). The publish methods
are the integration point: drive them from a live ``ExecutionEngine`` scan, or
replay a finished ``BacktestResult`` as a stream via :func:`serve_result`.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Mapping
from datetime import datetime

import polars as pl
from foxglove_websocket.server import FoxgloveServer
from foxglove_websocket.types import ChannelId
from google.protobuf.descriptor_pb2 import FileDescriptorSet

from super_trade.backtest.result import BacktestResult

from ._proto.supertrade.v1 import trade_pb2 as pb
from .export import _to_ns


def _b64_file_descriptor_set(msg_class: type) -> str:
    """Base64 ``FileDescriptorSet`` for ``msg_class`` (the Foxglove protobuf schema).

    Walks the message's file and its imports (e.g. ``google/protobuf/timestamp``)
    so the receiver can decode the message standalone.
    """
    fds = FileDescriptorSet()
    seen: set[str] = set()

    def add(file_descriptor) -> None:
        if file_descriptor.name in seen:
            return
        seen.add(file_descriptor.name)
        for dep in file_descriptor.dependencies:
            add(dep)
        file_descriptor.CopyToProto(fds.file.add())

    add(msg_class.DESCRIPTOR.file)
    return base64.b64encode(fds.SerializeToString()).decode("ascii")


class LiveBridge:
    """Advertises + publishes ``supertrade.v1`` messages on a ``FoxgloveServer``.

    Channels are registered lazily (first publish) or up front via :meth:`channel`.
    The ``publish_*`` coroutines mirror the MCAP exporter's topics: ``/equity``,
    ``/portfolio``, ``/fills``.
    """

    def __init__(self, server: FoxgloveServer) -> None:
        self._server = server
        self._channels: dict[str, ChannelId] = {}

    async def channel(self, topic: str, msg_class: type) -> ChannelId:
        """Register (once) and return the channel id for ``topic`` / ``msg_class``."""
        if topic not in self._channels:
            self._channels[topic] = await self._server.add_channel(
                {
                    "topic": topic,
                    "encoding": "protobuf",
                    "schemaName": msg_class.DESCRIPTOR.full_name,
                    "schema": _b64_file_descriptor_set(msg_class),
                    "schemaEncoding": "protobuf",
                }
            )
        return self._channels[topic]

    async def _send(self, topic: str, msg, ts_ns: int) -> None:
        chan = await self.channel(topic, type(msg))
        await self._server.send_message(chan, ts_ns, msg.SerializeToString())

    async def publish_equity(
        self, ts_ns: int, equity: float, cash: float, drawdown: float
    ) -> None:
        msg = pb.Equity(equity=equity, cash=cash, drawdown=drawdown)
        msg.time.FromNanoseconds(ts_ns)
        await self._send("/equity", msg, ts_ns)

    async def publish_portfolio(
        self, ts_ns: int, equity: float, cash: float, positions: list[Mapping]
    ) -> None:
        msg = pb.Portfolio(equity=equity, cash=cash, num_positions=len(positions))
        msg.time.FromNanoseconds(ts_ns)
        for p in positions:
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
        await self._send("/portfolio", msg, ts_ns)

    async def publish_bar(self, ts_ns: int, bar: Mapping) -> None:
        msg = pb.Bar(
            symbol=bar["symbol"],
            open=float(bar["open"]),
            high=float(bar["high"]),
            low=float(bar["low"]),
            close=float(bar["close"]),
            volume=float(bar["volume"]),
        )
        msg.time.FromNanoseconds(ts_ns)
        await self._send("/bars", msg, ts_ns)

    async def publish_fill(self, ts_ns: int, fill: Mapping) -> None:
        msg = pb.Fill(
            symbol=fill["symbol"],
            side=fill["side"],
            shares=int(fill["shares"]),
            price=float(fill["price"]),
            cost=float(fill["cost"]),
            notional=float(fill["notional"]),
            reason=fill["reason"],
        )
        msg.time.FromNanoseconds(ts_ns)
        await self._send("/fills", msg, ts_ns)


def _group_by_timestamp(frame: pl.DataFrame | None) -> dict[datetime, list[dict]]:
    """Bucket a telemetry frame's rows by their ``timestamp`` column."""
    out: dict[datetime, list[dict]] = {}
    if frame is None:
        return out
    for row in frame.iter_rows(named=True):
        ts = row["timestamp"]
        if ts is not None:
            out.setdefault(ts, []).append(row)
    return out


async def serve_result(
    result: BacktestResult,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    rate_hz: float = 8.0,
    loop: bool = True,
) -> None:
    """Replay a finished backtest over a Foxglove WebSocket server, bar by bar.

    Demonstrates the live path without a live broker: each bar's equity, portfolio
    snapshot, and fills are published at ``rate_hz`` bars/second, so a connected
    Foxglove shows the Trade Cockpit updating in real time. ``loop=True`` repeats
    forever so you can connect at any point.
    """
    eq = result.data.with_columns(
        (pl.col("equity") / pl.col("equity").cum_max() - 1).alias("drawdown")
    )
    eq_rows = list(eq.iter_rows(named=True))
    pos_by_ts = _group_by_timestamp(result.positions)
    fills_by_ts = _group_by_timestamp(result.fills)
    bars_by_ts = _group_by_timestamp(result.bars)
    delay = 1.0 / rate_hz if rate_hz > 0 else 0.0

    async with FoxgloveServer(
        host, port, "super-trade", supported_encodings=["protobuf"]
    ) as server:
        bridge = LiveBridge(server)
        # Advertise all topics up front so the panel sees them on connect.
        await bridge.channel("/bars", pb.Bar)
        await bridge.channel("/equity", pb.Equity)
        await bridge.channel("/portfolio", pb.Portfolio)
        await bridge.channel("/fills", pb.Fill)

        while True:
            for row in eq_rows:
                ts = row["timestamp"]
                ts_ns = _to_ns(ts)
                equity, cash = row["equity"], row["cash"]
                for bar in bars_by_ts.get(ts, []):
                    await bridge.publish_bar(ts_ns, bar)
                await bridge.publish_equity(ts_ns, equity, cash, row["drawdown"])
                if ts in pos_by_ts:
                    await bridge.publish_portfolio(ts_ns, equity, cash, pos_by_ts[ts])
                for fill in fills_by_ts.get(ts, []):
                    await bridge.publish_fill(ts_ns, fill)
                await asyncio.sleep(delay)
            if not loop:
                break
