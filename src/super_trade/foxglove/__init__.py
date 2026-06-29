"""Foxglove integration — stream a backtest to an MCAP log for visualization.

Turns a ``BacktestResult`` into an ``.mcap`` file you can scrub in Foxglove, with
``/equity``, ``/portfolio``, and ``/fills`` on one synchronized timeline. The
companion Foxglove extension (Trade Cockpit panel) lives in the ``foxglove-trade``
repo; the schemas are the buf-managed ``supertrade.v1`` protobuf package.

    from super_trade.foxglove import export_mcap
    export_mcap(result, "run.mcap")
"""

from __future__ import annotations

from .export import export_mcap

__all__ = ["export_mcap"]
