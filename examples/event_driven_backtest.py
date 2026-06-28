"""Event-driven backtest example.

Replays history bar-by-bar through the execution layer's SimBroker + RiskManager,
so it models path-dependent behaviour the vectorized engine can't — notably the
**stop-loss** — plus real cash, integer 手/lots, and per-name sizing.

Compare this with `vectorized_backtest.py`: same strategies, same data, different
engine. The event-driven numbers differ because they reflect real share lots, a
cash budget, per-name position caps, and an 8% stop-loss.

Run:
    uv run python examples/event_driven_backtest.py [SYMBOL] [DATABASE] [INTERVAL]

Defaults to FAKE003, daily, in super_trade_sandbox. INTERVAL is one of
1m/5m/15m/30m/1h/1d; intraday intervals are resampled from stored 1-minute bars
(seed them with `python scripts/seed_sandbox.py minute`).
"""

from __future__ import annotations

import sys

from super_trade.backtest import BuyAndHold, RsiReversion, SmaCross
from super_trade.data import ClickHouseConfig, ClickHouseStore, Interval, load_bars
from super_trade.execution import EventDrivenBacktest, RiskLimits, RiskManager


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "FAKE003"
    database = sys.argv[2] if len(sys.argv) > 2 else "super_trade_sandbox"
    interval = Interval(sys.argv[3]) if len(sys.argv) > 3 else Interval.DAY
    # Intraday intervals are derived from stored 1-minute bars by resampling.
    base = Interval.MINUTE if interval.is_intraday else None
    cash = 1_000_000.0

    with ClickHouseStore(ClickHouseConfig(database=database)) as store:
        if load_bars(store, symbol, interval, resample_from=base).height == 0:
            print(f"No bars for {symbol} in {database}. Seed the sandbox or backfill.")
            return

        print(
            f"Event-driven backtest of {symbol} "
            f"({interval.value} bars, cash CNY {cash:,.0f}, 8% stop)\n"
        )

        for strategy in (BuyAndHold(), SmaCross(10, 30), RsiReversion(14, 30, 70)):
            result = EventDrivenBacktest(
                store,
                strategy,
                cash=cash,
                universe=[symbol],
                interval=interval,
                resample_from=base,
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
            interval=interval,
            resample_from=base,
            risk=RiskManager(RiskLimits(stop_loss=0.08)),
        ).run()
        result.equity_curve().write_html("/tmp/event_driven_equity.html")
        print("\nEquity curve written to /tmp/event_driven_equity.html")


if __name__ == "__main__":
    main()
