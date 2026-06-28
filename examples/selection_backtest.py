"""Selection + allocation + backtest — the full cross-sectional pipeline.

Shows the layer above per-symbol strategies:

    select (which names)  ->  allocate (how much each)  ->  event-driven backtest

1. Build a feature cross-section from the store (OHLCV-derived: liquidity, volatility,
   momentum) joined with a small *demo* fundamentals frame (流通市值 / 机构持股 / ST).
2. Select a "retail-pond" universe — small float cap, tradeable-but-not-quant-sized
   liquidity, low institutional ownership, no ST — the corner where 散户 dominate.
3. Allocate across the picks with inverse-volatility weights (equal risk per name).
4. Backtest the strategy on that universe with those weights as the portfolio budget.

Run (after seeding the sandbox: `python scripts/seed_sandbox.py`):
    uv run python examples/selection_backtest.py [DATABASE]

NOTE: the fundamentals here are fabricated demo values for the FAKE sandbox names —
real 流通市值 / 机构持股 ingestion is future work. And small-cap backtests need
delisted names in the data or they overstate returns (survivorship bias).
"""

from __future__ import annotations

import sys

import polars as pl

from super_trade.backtest import SmaCross
from super_trade.data import ClickHouseConfig, ClickHouseStore, Interval
from super_trade.execution import EventDrivenBacktest, RiskLimits, RiskManager
from super_trade.portfolio import InverseVol
from super_trade.selection import (
    AtMost,
    Flag,
    Range,
    Rank,
    Selector,
    build_features,
)


def main() -> None:
    database = sys.argv[1] if len(sys.argv) > 1 else "super_trade_sandbox"

    with ClickHouseStore(ClickHouseConfig(database=database)) as store:
        symbols = store.list_symbols(Interval.DAY)
        if not symbols:
            print(f"No daily bars in {database}. Seed: python scripts/seed_sandbox.py")
            return

        # --- demo fundamentals (assumed-available data; fabricated for the sandbox) ---
        # Cycle through plausible values so the filters have something to bite on.
        mktcaps = [8e9, 3e9, 50e9, 1.5e9, 200e9]
        insts = [0.10, 0.05, 0.45, 0.08, 0.60]
        fundamentals = pl.DataFrame(
            {
                "symbol": symbols,
                "float_mktcap": [
                    mktcaps[i % len(mktcaps)] for i in range(len(symbols))
                ],
                "inst_ownership": [insts[i % len(insts)] for i in range(len(symbols))],
                "is_st": [False] * len(symbols),
            }
        )

        # --- 1. feature cross-section ---
        feats = build_features(store, symbols, fundamentals=fundamentals)

        # --- 2. select the retail-pond universe ---
        pond = Selector(
            filters=[
                Range("float_mktcap", high=10e9),  # small float cap
                AtMost("inst_ownership", 0.20),  # low institutional ownership
                ~Flag("is_st"),  # exclude ST / *ST
            ],
            score=Rank("inst_ownership", ascending=True)  # less quant-crowded first
            + Rank("momentum", ascending=False),  # ...then recent strength
            top_n=3,
        )
        universe = pond.select(feats)
        print(f"Selected universe ({len(universe)}): {universe}")
        if not universe:
            print("Nothing passed the filters — relax them or seed more symbols.")
            return

        # --- 3. allocate across the picks (inverse volatility) ---
        picks = feats.filter(pl.col("symbol").is_in(universe))
        weights = InverseVol(gross=0.9, max_weight=0.4).weights(picks)
        print("Inverse-vol weights:")
        for sym, w in sorted(weights.items(), key=lambda kv: -kv[1]):
            print(f"  {sym}  {w:.1%}")

        # --- 4. backtest on the selected universe with those weights ---
        result = EventDrivenBacktest(
            store,
            SmaCross(10, 30),
            cash=1_000_000,
            universe=universe,
            weights=weights,
            risk=RiskManager(RiskLimits(stop_loss=0.08)),
        ).run()
        s = result.stats()
        print(
            f"\nPortfolio backtest (SmaCross): total={s['total_return']:+.2%}  "
            f"sharpe={s['sharpe']:+.2f}  maxDD={s['max_drawdown']:.2%}"
        )


if __name__ == "__main__":
    main()
