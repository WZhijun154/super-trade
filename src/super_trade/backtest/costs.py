"""Transaction-cost model for backtests (China A-share defaults).

Charges, per bar, on the change in held weight (turnover):
* **commission** — brokerage fee, both sides (~2.5 bp), with a **¥5 per-order floor**.
* **stamp tax (印花税)** — 5 bp, **sell side only** (the rate since 2023-08-28; the
  sell-only asymmetry matters).
* **transfer fee (过户费)** — 0.1 bp, both sides.
* **slippage** — a flat bp cost on turnover.

Two surfaces share these rates so backtest and live charge alike:
* :meth:`CostModel.cost_expr` — vectorized, in fractional *weights* (subtracts
  straight from the period return). The ¥5 floor can't apply here (no share lots,
  only weights), so it's intentionally ignored.
* :meth:`CostModel.trade_cost` — absolute ¥ for one share-lot trade, used by the
  ``SimBroker``; this one *does* apply the ¥5 floor.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class CostModel:
    """Per-turnover transaction costs (China A-share defaults)."""

    commission_rate: float = 0.00025
    stamp_tax_rate: float = 0.0005  # 印花税, sell side only (rate since 2023-08-28)
    transfer_fee_rate: float = 0.00001  # 过户费, both sides
    slippage_rate: float = 0.0001
    min_commission: float = 5.0  # ¥ per order floor (trade_cost only — see module doc)

    def cost_expr(self, held_col: str = "held") -> pl.Expr:
        """Cost (as a return drag) for the trade entering each bar.

        Both-sides charges (commission, transfer fee, slippage) hit the full
        turnover; the sell-only stamp tax hits just the reduction. The ¥5 floor is
        omitted here — weights carry no share notional to apply it to.
        """
        held = pl.col(held_col)
        change = held - held.shift(1).fill_null(0.0)
        turnover = change.abs()
        sold = (-change).clip(lower_bound=0.0)  # positive only when reducing
        both_sides = self.commission_rate + self.transfer_fee_rate + self.slippage_rate
        return turnover * both_sides + sold * self.stamp_tax_rate

    def trade_cost(self, notional: float, *, is_sell: bool) -> float:
        """Absolute cost (¥) for a single trade of the given notional.

        Reuses the same rates as the vectorized model so backtest and live charge
        costs consistently, but adds the two share-level details the weight-based
        ``cost_expr`` can't express: the **¥5 commission floor** and (since stamp
        tax is sell-only) the sell-side asymmetry. Transfer fee + slippage apply
        both sides.
        """
        commission = max(notional * self.commission_rate, self.min_commission)
        cost = commission + notional * (self.transfer_fee_rate + self.slippage_rate)
        if is_sell:
            cost += notional * self.stamp_tax_rate
        return cost


# A zero-cost model, handy for tests and frictionless comparisons.
NO_COSTS = CostModel(
    commission_rate=0.0,
    stamp_tax_rate=0.0,
    transfer_fee_rate=0.0,
    slippage_rate=0.0,
    min_commission=0.0,
)
