"""Transaction-cost model for backtests (China A-share defaults).

Charges, per bar, on the change in held weight (turnover):
* **commission** — brokerage fee, both sides (~2.5 bp).
* **stamp tax (印花税)** — 10 bp, **sell side only** (the asymmetry matters).
* **slippage** — a flat bp cost on turnover.

Costs are expressed as a fraction of weight (so they subtract directly from the
period return). The per-trade ¥5 commission floor is intentionally ignored — the
vectorized engine works in fractional weights, not share lots.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class CostModel:
    """Per-turnover transaction costs."""

    commission_rate: float = 0.00025
    stamp_tax_rate: float = 0.001  # sell side only
    slippage_rate: float = 0.0001

    def cost_expr(self, held_col: str = "held") -> pl.Expr:
        """Cost (as a return drag) for the trade entering each bar."""
        held = pl.col(held_col)
        change = held - held.shift(1).fill_null(0.0)
        turnover = change.abs()
        sold = (-change).clip(lower_bound=0.0)  # positive only when reducing
        return turnover * (self.commission_rate + self.slippage_rate) + (
            sold * self.stamp_tax_rate
        )

    def trade_cost(self, notional: float, *, is_sell: bool) -> float:
        """Absolute cost (¥) for a single trade of the given notional.

        Reuses the same rates as the vectorized model, so backtest and live
        execution charge costs consistently. Stamp tax applies to sells only.
        """
        cost = notional * (self.commission_rate + self.slippage_rate)
        if is_sell:
            cost += notional * self.stamp_tax_rate
        return cost


# A zero-cost model, handy for tests and frictionless comparisons.
NO_COSTS = CostModel(commission_rate=0.0, stamp_tax_rate=0.0, slippage_rate=0.0)
