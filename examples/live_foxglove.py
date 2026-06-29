"""Stream a backtest to Foxglove live over a WebSocket.

Runs a backtest, then replays it bar-by-bar over the Foxglove WebSocket protocol so
a connected Foxglove shows the Trade Cockpit updating in real time — the same
publish path a live ``ExecutionEngine`` scan would drive.

Run (after seeding the sandbox: `python scripts/seed_sandbox.py`):
    uv run python examples/live_foxglove.py [SYMBOL] [DATABASE]

Then in Foxglove: Open connection -> Foxglove WebSocket -> ws://127.0.0.1:8765,
and add the Trade Cockpit panel. Ctrl-C to stop.
"""

from __future__ import annotations

import asyncio
import sys

from super_trade.backtest import SmaCross
from super_trade.data import ClickHouseConfig, ClickHouseStore, Interval
from super_trade.execution import EventDrivenBacktest, RiskLimits, RiskManager
from super_trade.foxglove import serve_result


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "FAKE003"
    database = sys.argv[2] if len(sys.argv) > 2 else "super_trade_sandbox"

    with ClickHouseStore(ClickHouseConfig(database=database)) as store:
        if store.read_bars(symbol, Interval.DAY).height == 0:
            print(f"No bars for {symbol} in {database}. Seed or backfill first.")
            return
        result = EventDrivenBacktest(
            store,
            SmaCross(10, 30),
            cash=1_000_000,
            universe=[symbol],
            risk=RiskManager(RiskLimits(stop_loss=0.08)),
        ).run()

    print("Foxglove WebSocket: ws://127.0.0.1:8765")
    print("In Foxglove: Open connection -> Foxglove WebSocket, add Trade Cockpit.")
    print("Ctrl-C to stop.")
    try:
        asyncio.run(serve_result(result, rate_hz=8.0))
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
