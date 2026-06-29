"""Foxglove integration — stream a backtest to an MCAP log for visualization.

Turns a ``BacktestResult`` into an ``.mcap`` file you can scrub in Foxglove, with
``/equity``, ``/portfolio``, and ``/fills`` on one synchronized timeline. The
companion Foxglove extension (Trade Cockpit panel) lives in the ``foxglove-trade``
repo; the schemas are the buf-managed ``supertrade.v1`` protobuf package.

    from super_trade.foxglove import export_mcap
    export_mcap(result, "run.mcap")               # offline: scrub an .mcap

    import asyncio
    from super_trade.foxglove import serve_result
    asyncio.run(serve_result(result))             # live: stream over WebSocket
"""

from __future__ import annotations

from .export import export_mcap
from .live import LiveBridge, serve_result

__all__ = ["LiveBridge", "export_mcap", "serve_result"]
