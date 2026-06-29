"""Transaction-cost model for backtests (China A-share defaults).

Charges, per bar, on the change in held weight (turnover):
* **commission** — brokerage fee, both sides (~2.5 bp), with a **¥5 per-order floor**.
* **stamp tax (印花税)** — 5 bp, **sell side only** (the rate since 2023-08-28; the
  sell-only asymmetry matters).
* **transfer fee (过户费)** — 0.1 bp, both sides.
* **slippage** — a base bp on turnover, **plus a size/liquidity-dependent market
  impact**: the more of a bar's volume you take, the worse your fill. Modelled as
  ``impact_coef * sqrt(participation)`` (the classic square-root impact law, where
  ``participation = order shares / bar volume``). This is what makes trading thin
  names cost what it really costs — crucial for illiquid / small-cap strategies.

Two surfaces share these rates so backtest and live charge alike:
* :meth:`CostModel.cost_expr` — vectorized, in fractional *weights* (subtracts
  straight from the period return). The ¥5 floor and market impact can't apply here
  (no share lots / bar volume, only weights), so they're intentionally ignored.
* :meth:`CostModel.trade_cost` — absolute ¥ for one share-lot trade, used by the
  ``SimBroker``; this one applies the ¥5 floor and the participation-based impact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class CostModel:
    """Per-turnover transaction costs (China A-share defaults)."""

    commission_rate: float = 0.00025
    stamp_tax_rate: float = 0.0005  # 印花税, sell side only (rate since 2023-08-28)
    transfer_fee_rate: float = 0.00001  # 过户费, both sides
    slippage_rate: float = 0.0001  # base half-spread slippage on turnover
    # Market-impact coefficient: extra slippage = impact_coef * sqrt(participation),
    # participation = order shares / bar volume. e.g. taking 10% of a bar adds
    # impact_coef*0.32; at 0.1 that's ~3.2%. Tune to your venue; 0 disables impact.
    impact_coef: float = 0.1
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

    def trade_cost(
        self, notional: float, *, is_sell: bool, participation: float = 0.0
    ) -> float:
        """Absolute cost (¥) for a single trade of the given notional.

        Reuses the same rates as the vectorized model so backtest and live charge
        costs consistently, but adds the share-level details the weight-based
        ``cost_expr`` can't express: the **¥5 commission floor**, the sell-only stamp
        tax, and **market impact**. Transfer fee + base slippage apply both sides.

        Args:
            notional: Trade value in ¥ (shares * price).
            is_sell: Whether this is a sell (adds stamp tax).
            participation: Order shares / the bar's volume — drives the impact term
                ``impact_coef * sqrt(participation)``. 0 (the default, e.g. live
                orders with no bar context) means no modelled impact.

        Returns:
            Total ¥ cost: commission (floored) + transfer + (base + impact) slippage
            + sell-side stamp tax.
        """
        commission = max(notional * self.commission_rate, self.min_commission)
        impact = self.impact_coef * math.sqrt(max(participation, 0.0))
        cost = commission + notional * (
            self.transfer_fee_rate + self.slippage_rate + impact
        )
        if is_sell:
            cost += notional * self.stamp_tax_rate
        return cost


# A zero-cost model, handy for tests and frictionless comparisons.
NO_COSTS = CostModel(
    commission_rate=0.0,
    stamp_tax_rate=0.0,
    transfer_fee_rate=0.0,
    slippage_rate=0.0,
    impact_coef=0.0,
    min_commission=0.0,
)
