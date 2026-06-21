"""Event-driven backtest example.

Replays history bar-by-bar through the execution layer's SimBroker + RiskManager,
so it models path-dependent behaviour the vectorized engine can't — notably the
**stop-loss** — plus real cash, integer 手/lots, and per-name sizing.

Compare this with `vectorized_backtest.py`: same strategies, same data, different
engine. The event-driven numbers differ because they reflect real share lots, a
cash budget, per-name position caps, and an 8% stop-loss.

Run:
    uv run python examples/event_driven_backtest.py [SYMBOL] [DATABASE]

Defaults to FAKE003 in super_trade_sandbox.
"""

from __future__ import annotations

import sys

from super_trade.backtest import BuyAndHold, RsiReversion, SmaCross
from super_trade.data import ClickHouseConfig, ClickHouseStore, Interval
from super_trade.execution import EventDrivenBacktest, RiskLimits, RiskManager


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "FAKE003"
    database = sys.argv[2] if len(sys.argv) > 2 else "super_trade_sandbox"
    cash = 1_000_000.0

    with ClickHouseStore(ClickHouseConfig(database=database)) as store:
        if store.read_bars(symbol, Interval.DAY).height == 0:
            print(f"No bars for {symbol} in {database}. Seed the sandbox or backfill.")
            return

        print(f"Event-driven backtest of {symbol} (cash CNY {cash:,.0f}, 8% stop)\n")

        for strategy in (BuyAndHold(), SmaCross(10, 30), RsiReversion(14, 30, 70)):
            # A fresh RiskManager per run — it carries intraday state.
            result = EventDrivenBacktest(
                store,
                strategy,
                cash=cash,
                universe=[symbol],
                risk=RiskManager(RiskLimits(stop_loss=0.08)),
            ).run()
            s = result.stats()
            print(
                f"{strategy.name:20}  total={s['total_return']:+.2%}  "
                f"cagr={s['cagr']:+.2%}  sharpe={s['sharpe']:+.2f}  "
                f"maxDD={s['max_drawdown']:.2%}"
            )

        # Save one equity curve to HTML you can open in a browser.
        result = EventDrivenBacktest(
            store,
            SmaCross(10, 30),
            cash=cash,
            universe=[symbol],
            risk=RiskManager(RiskLimits(stop_loss=0.08)),
        ).run()
        result.equity_curve().write_html("/tmp/event_driven_equity.html")
        print("\nEquity curve written to /tmp/event_driven_equity.html")


if __name__ == "__main__":
    main()
