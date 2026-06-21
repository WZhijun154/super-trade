"""Vectorized backtest example.

Fast, signal-research backtest: the strategy's target weights are turned into P&L
over the whole price frame at once (no bar-by-bar loop, no path-dependent logic).

Run:
    uv run python examples/vectorized_backtest.py [SYMBOL] [DATABASE]

Defaults to FAKE003 in the super_trade_sandbox database (realistic synthetic data
from scripts/seed_sandbox.py). Use a real symbol + the `super_trade` database once
you have backfilled real bars.
"""

from __future__ import annotations

import sys

from super_trade.backtest import (
    BuyAndHold,
    CostModel,
    RsiReversion,
    SmaCross,
    VectorizedEngine,
)
from super_trade.data import ClickHouseConfig, ClickHouseStore, Interval


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "FAKE003"
    database = sys.argv[2] if len(sys.argv) > 2 else "super_trade_sandbox"

    with ClickHouseStore(ClickHouseConfig(database=database)) as store:
        bars = store.read_bars(symbol, Interval.DAY)

    if bars.height == 0:
        print(
            f"No bars for {symbol} in {database}. Seed the sandbox or backfill first."
        )
        return

    print(f"Backtesting {symbol} ({bars.height} daily bars) from {database}\n")

    # The same DataFrame is reused for each strategy; the engine charges A-share
    # costs (commission, stamp tax on sells, slippage) via the default CostModel.
    engine = VectorizedEngine(CostModel())
    for strategy in (BuyAndHold(), SmaCross(10, 30), RsiReversion(14, 30, 70)):
        result = engine.run(bars, strategy)
        s = result.stats()
        print(
            f"{strategy.name:20}  total={s['total_return']:+.2%}  "
            f"cagr={s['cagr']:+.2%}  sharpe={s['sharpe']:+.2f}  "
            f"maxDD={s['max_drawdown']:.2%}"
        )

    # Save one equity curve to HTML you can open in a browser.
    fig = engine.run(bars, SmaCross(10, 30)).equity_curve()
    out = "/tmp/vectorized_equity.html"
    fig.write_html(out)
    print(f"\nEquity curve written to {out}")


if __name__ == "__main__":
    main()
