"""QMT live broker via ``xtquant.xttrader`` (use a SIMULATION account).

Sends real orders to a running MiniQMT terminal, so the engine should only call
it with ``dry_run=False`` after validating in dry-run. ``xtquant`` is imported
lazily, so this module loads anywhere; the trading path must be verified on a
machine running MiniQMT with trading enabled.

VERIFY ON A MiniQMT MACHINE (cannot be tested in CI/Linux):
* the ``XtQuantTrader`` connect/session flow and your ``account_id``;
* the exact ``order_stock`` arguments and ``xtconstant`` values for your version;
* position/asset query field names;
* volume units (shares vs 手) and price-type semantics.
"""

from __future__ import annotations

from typing import Any

import logfire

from super_trade.sources.qmt_source import to_qmt_symbol

from .broker import Broker, Fill, Order, Position, Side


class QmtBroker(Broker):
    """Place orders on a (simulation) QMT account through MiniQMT."""

    def __init__(
        self,
        account_id: str,
        *,
        mini_qmt_path: str,
        session_id: int = 1,
    ) -> None:
        self._account_id = account_id
        self._path = mini_qmt_path
        self._session_id = session_id
        self._trader: Any = None
        self._account: Any = None

    def connect(self) -> None:
        """Connect to MiniQMT and subscribe the account (call once at startup)."""
        from xtquant.xttrader import XtQuantTrader
        from xtquant.xttype import StockAccount

        trader = XtQuantTrader(self._path, self._session_id)
        trader.start()
        if trader.connect() != 0:
            raise RuntimeError("could not connect to MiniQMT trader")
        account = StockAccount(self._account_id)
        if trader.subscribe(account) != 0:
            raise RuntimeError(f"could not subscribe account {self._account_id}")
        self._trader = trader
        self._account = account
        logfire.info("QMT trader connected", account=self._account_id)

    def _require(self) -> Any:
        if self._trader is None:
            raise RuntimeError("QmtBroker.connect() must be called first")
        return self._trader

    def cash(self) -> float:
        asset = self._require().query_stock_asset(self._account)
        return float(getattr(asset, "cash", 0.0)) if asset else 0.0

    def positions(self) -> dict[str, Position]:
        out: dict[str, Position] = {}
        for p in self._require().query_stock_positions(self._account) or []:
            symbol = str(p.stock_code).split(".", 1)[0]
            volume = int(getattr(p, "volume", 0))
            if volume > 0:
                out[symbol] = Position(
                    symbol=symbol,
                    shares=volume,
                    avg_price=float(getattr(p, "open_price", 0.0)),
                )
        return out

    def place_order(self, order: Order) -> Fill | None:
        from xtquant import xtconstant

        trader = self._require()
        order_type = (
            xtconstant.STOCK_BUY if order.side == Side.BUY else xtconstant.STOCK_SELL
        )
        order_id = trader.order_stock(
            self._account,
            to_qmt_symbol(order.symbol),
            order_type,
            order.shares,
            xtconstant.FIX_PRICE,
            order.price,
            order.reason or "super-trade",
            "",
        )
        if order_id is None or order_id < 0:
            logfire.warn("QMT order submission failed: {symbol}", symbol=order.symbol)
            return None
        # Submission only; the actual fill arrives via QMT's trade callbacks. Wire
        # XtQuantTraderCallback.on_stock_trade to reconcile real fills/costs.
        logfire.info(
            "QMT order submitted",
            order_id=order_id,
            symbol=order.symbol,
            side=order.side.value,
            shares=order.shares,
        )
        return Fill(
            symbol=order.symbol,
            side=order.side,
            shares=order.shares,
            price=order.price,
            cost=0.0,
            reason=order.reason,
        )
