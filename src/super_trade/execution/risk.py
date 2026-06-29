"""Risk management — the safety layer between signals and orders.

Even on a simulation account, every order passes through these guardrails:
per-name size cap, gross-exposure cap, a daily-loss halt, an order-count cap, a
stop-loss, and a manual kill switch. Position sizing rounds down to whole board
lots and respects available cash.
"""

from __future__ import annotations

from dataclasses import dataclass

from .broker import LOT_SIZE, Broker, Position


@dataclass(frozen=True)
class RiskLimits:
    """Configurable risk caps (fractions of account equity unless noted)."""

    max_position_weight: float = 0.2  # ≤ 20% of equity per name
    max_gross_exposure: float = 0.95  # ≤ 95% invested (keep cash buffer)
    max_daily_loss: float = 0.05  # halt trading if down 5% on the day
    stop_loss: float = 0.08  # exit a name down 8% from entry
    max_orders_per_day: int = 200


class RiskManager:
    """Enforces :class:`RiskLimits` and tracks intraday state."""

    def __init__(
        self, limits: RiskLimits | None = None, lot_size: int = LOT_SIZE
    ) -> None:
        self.limits = limits or RiskLimits()
        self._lot = lot_size
        self.halted = False
        self._day_start_equity: float | None = None
        self._orders_today = 0

    def start_day(self, equity: float) -> None:
        """Reset daily counters; call once at the start of each session."""
        self._day_start_equity = equity
        self._orders_today = 0
        self.halted = False

    def kill(self) -> None:
        """Manual kill switch — blocks all further orders this session."""
        self.halted = True

    def update_daily_loss(self, equity: float) -> bool:
        """Halt (and return True) if the daily loss limit is breached."""
        if self._day_start_equity is not None and equity <= self._day_start_equity * (
            1 - self.limits.max_daily_loss
        ):
            self.halted = True
        return self.halted

    def stop_price(self, position: Position) -> float:
        """The price at/below which the position's stop-loss fires."""
        return position.avg_price * (1 - self.limits.stop_loss)

    def stop_triggered(self, position: Position, price: float) -> bool:
        """True if ``price`` is at/below the position's stop-loss level.

        Pass the bar's **low** to detect an intrabar trigger (the stop fires even if
        the close later recovers above the level).
        """
        return price <= self.stop_price(position)

    def can_trade(self) -> bool:
        return not self.halted and self._orders_today < self.limits.max_orders_per_day

    def record_order(self) -> None:
        self._orders_today += 1

    def max_buy_shares(
        self, symbol: str, price: float, equity: float, broker: Broker
    ) -> int:
        """Largest lot-aligned buy allowed by per-name, exposure, and cash caps."""
        if not self.can_trade() or price <= 0:
            return 0
        # per-name cap: target weight of equity, minus what we already hold
        held_value = broker.shares(symbol) * price
        name_budget = max(0.0, self.limits.max_position_weight * equity - held_value)
        # gross-exposure cap across the whole book
        invested = sum(
            p.shares * price if s == symbol else p.shares * p.avg_price
            for s, p in broker.positions().items()
        )
        gross_budget = max(0.0, self.limits.max_gross_exposure * equity - invested)
        budget = min(name_budget, gross_budget, broker.cash())
        lots = int(budget // (price * self._lot))
        return lots * self._lot
