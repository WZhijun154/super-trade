"""Event-driven backtest example — on **1-minute** bars.

Replays history bar-by-bar through the execution layer's SimBroker + RiskManager,
so it models path-dependent behaviour the vectorized engine can't — notably the
**stop-loss** — plus real cash, integer 手/lots, and per-name sizing. Here the
simulation clock ticks once per *minute* (A-share sessions 09:30-11:30 / 13:00-15:00).

Compare this with `vectorized_backtest.py`: same strategies, same data, different
engine. The event-driven numbers differ because they reflect real share lots, a
cash budget, per-name position caps, and an 8% stop-loss — plus A-share market
rules (T+1, 涨跌停 price limits, 停牌 suspension, volume-based partial fills) that
are on by default via `MarketRules`.

Prerequisite — seed 1-minute sandbox data once:
    uv run python scripts/seed_sandbox.py minute

Run:
    uv run python examples/event_driven_backtest.py [SYMBOL] [DATABASE] [INTERVAL]

Defaults to FAKE001 at 1m in super_trade_sandbox. INTERVAL is one of
1m/5m/15m/30m/1h/1d; any intraday interval is resampled from the stored 1-minute
bars on read, so the same minute data backs every granularity.
"""

from __future__ import annotations

import sys

from super_trade.backtest import BuyAndHold, RsiReversion, ScaledRsiReversion, SmaCross
from super_trade.data import ClickHouseConfig, ClickHouseStore, Interval, load_bars
from super_trade.execution import EventDrivenBacktest, RiskLimits, RiskManager


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "FAKE001"
    database = sys.argv[2] if len(sys.argv) > 2 else "super_trade_sandbox"
    interval = Interval(sys.argv[3]) if len(sys.argv) > 3 else Interval.MINUTE
    # 1-minute is stored directly; coarser intraday intervals resample from it.
    base = Interval.MINUTE if interval.is_intraday else None
    cash = 1_000_000.0

    with ClickHouseStore(ClickHouseConfig(database=database)) as store:
        if load_bars(store, symbol, interval, resample_from=base).height == 0:
            print(
                f"No 1-minute bars for {symbol} in {database}. "
                "Seed them first: uv run python scripts/seed_sandbox.py minute"
            )
            return

        print(
            f"Event-driven backtest of {symbol} "
            f"({interval.value} bars, cash CNY {cash:,.0f}, 8% stop)\n"
        )

        # ScaledRsiReversion emits a *fractional* target weight → the engine scales
        # the position in and out in tranches (many fills per name), unlike the
        # all-or-nothing strategies above.
        strategies = (
            BuyAndHold(),
            SmaCross(10, 30),
            RsiReversion(14, 30, 70),
            ScaledRsiReversion(14, 30, 70),
        )
        for strategy in strategies:
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
