"""Periodic rebalance — re-select + re-allocate on a schedule, then backtest.

Where `selection_backtest.py` chooses the universe + weights *once*, this re-runs
selection and allocation every N trading days and feeds the engine a time-varying
budget schedule. A name dropped at a rebalance gets weight 0 and is scaled out; a
newly selected one is scaled in — all through the same delta-rebalance loop.

Run (after seeding the sandbox: `python scripts/seed_sandbox.py`):
    uv run python examples/periodic_rebalance.py [DATABASE]

NOTE: fundamentals are fabricated demo values for the FAKE names, and the schedule
uses a single static fundamentals frame — real, time-varying fundamentals ingestion
is future work. Small-cap backtests also need delisted names (survivorship bias).
"""

from __future__ import annotations

import sys

import polars as pl

from super_trade.backtest import SmaCross
from super_trade.data import ClickHouseConfig, ClickHouseStore, Interval
from super_trade.execution import EventDrivenBacktest, RiskLimits, RiskManager
from super_trade.portfolio import InverseVol, periodic_schedule
from super_trade.selection import AtMost, Flag, Range, Rank, Selector


def main() -> None:
    database = sys.argv[1] if len(sys.argv) > 1 else "super_trade_sandbox"

    with ClickHouseStore(ClickHouseConfig(database=database)) as store:
        symbols = store.list_symbols(Interval.DAY)
        if not symbols:
            print(f"No daily bars in {database}. Seed: python scripts/seed_sandbox.py")
            return

        # Demo fundamentals (fabricated for the sandbox FAKE names).
        mktcaps = [8e9, 3e9, 50e9, 1.5e9, 200e9]
        insts = [0.10, 0.05, 0.45, 0.08, 0.60]
        fundamentals = pl.DataFrame(
            {
                "symbol": symbols,
                "float_mktcap": [mktcaps[i % 5] for i in range(len(symbols))],
                "inst_ownership": [insts[i % 5] for i in range(len(symbols))],
                "is_st": [False] * len(symbols),
            }
        )

        selector = Selector(
            filters=[
                Range("float_mktcap", high=10e9),  # small float cap
                AtMost("inst_ownership", 0.20),  # low institutional ownership
                ~Flag("is_st"),
            ],
            score=Rank("inst_ownership", ascending=True)
            + Rank("momentum", ascending=False),
            top_n=3,
        )

        # Re-select + re-allocate every ~month (21 trading days) after a 40-day warm-up.
        universe, schedule = periodic_schedule(
            store,
            selector,
            InverseVol(gross=0.9, max_weight=0.4),
            symbols=symbols,
            every=21,
            lookback=40,
            fundamentals=fundamentals,
        )
        print(f"Union universe ({len(universe)}): {universe}")
        print(f"Rebalances: {len(schedule)}")
        for d, w in schedule:
            picks = ", ".join(f"{s} {v:.0%}" for s, v in sorted(w.items()))
            print(f"  {d}: {picks or '(flat)'}")

        if not universe:
            print("Nothing ever qualified — relax the filters or seed more symbols.")
            return

        result = EventDrivenBacktest(
            store,
            SmaCross(10, 30),
            cash=1_000_000,
            universe=universe,
            weight_schedule=schedule,
            risk=RiskManager(RiskLimits(stop_loss=0.08)),
        ).run()
        s = result.stats()
        print(
            f"\nPeriodic-rebalance backtest: total={s['total_return']:+.2%}  "
            f"sharpe={s['sharpe']:+.2f}  maxDD={s['max_drawdown']:.2%}"
        )


if __name__ == "__main__":
    main()
