"""Vectorized backtest example.

Fast, signal-research backtest: the strategy's target weights are turned into P&L
over the whole price frame at once (no bar-by-bar loop, no path-dependent logic).

Run:
    uv run python examples/vectorized_backtest.py [SYMBOL] [DATABASE] [INTERVAL]

Defaults to FAKE003, daily, in the super_trade_sandbox database (synthetic data
from scripts/seed_sandbox.py). INTERVAL is one of 1m/5m/15m/30m/1h/1d; intraday
intervals are resampled from stored 1-minute bars (seed them with
`python scripts/seed_sandbox.py minute`, e.g. FAKE001 5m).
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
from super_trade.data import ClickHouseConfig, ClickHouseStore, Interval, load_bars


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "FAKE003"
    database = sys.argv[2] if len(sys.argv) > 2 else "super_trade_sandbox"
    interval = Interval(sys.argv[3]) if len(sys.argv) > 3 else Interval.DAY
    # Intraday intervals are derived from stored 1-minute bars by resampling.
    base = Interval.MINUTE if interval.is_intraday else None

    with ClickHouseStore(ClickHouseConfig(database=database)) as store:
        bars = load_bars(store, symbol, interval, resample_from=base)

    if bars.height == 0:
        print(
            f"No bars for {symbol} in {database}. Seed the sandbox or backfill first."
        )
        return

    print(
        f"Backtesting {symbol} ({bars.height} {interval.value} bars) from {database}\n"
    )

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
    out = "/home/wangzhijun/Projects/super-trade/vectorized_equity.html"
    fig.write_html(out)
    print(f"\nEquity curve written to {out}")


if __name__ == "__main__":
    main()
