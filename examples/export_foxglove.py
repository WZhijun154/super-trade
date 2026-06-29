"""Export an event-driven backtest to an MCAP log for Foxglove.

Runs a backtest and writes ``/equity``, ``/portfolio``, and ``/fills`` to an
``.mcap`` you can open + scrub in Foxglove (install the Trade Cockpit extension
from the foxglove-trade repo for the positions/fills panel).

Run (after seeding the sandbox: `python scripts/seed_sandbox.py`):
    uv run python examples/export_foxglove.py [SYMBOL] [DATABASE] [OUT.mcap]
"""

from __future__ import annotations

import sys

from super_trade.backtest import SmaCross
from super_trade.data import ClickHouseConfig, ClickHouseStore, Interval
from super_trade.execution import EventDrivenBacktest, RiskLimits, RiskManager
from super_trade.foxglove import export_mcap


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "FAKE003"
    database = sys.argv[2] if len(sys.argv) > 2 else "super_trade_sandbox"
    out = sys.argv[3] if len(sys.argv) > 3 else "/tmp/super_trade.mcap"

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

    path = export_mcap(result, out)
    fills = 0 if result.fills is None else result.fills.height
    print(f"Wrote {path} — {result.data.height} bars, {fills} fills.")
    print("Open it in Foxglove (foxglove.dev) and scrub the timeline.")


if __name__ == "__main__":
    main()
