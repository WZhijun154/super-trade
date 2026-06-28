"""A-share market rules for the event-driven backtest.

These model the *market* (not the account): when an order would not have filled,
and at what size. They are applied in :class:`EventDrivenBacktest`'s bar loop —
the ``SimBroker`` stays a pure fill engine. All knobs default to the realistic
setting; pass a tweaked :class:`MarketRules` to relax them.

Modelled here:

* **T+1** — shares bought today cannot be sold until the next trading day.
* **涨跌停 (price limits)** — no counterparty at the limit, so you cannot BUY at
  the upper limit or SELL at the lower limit. The band width depends on the board
  and is inferred from the symbol's code prefix (see :func:`limit_pct`).
* **停牌 (suspension)** — a bar that did not trade (``volume == 0``, or no bar at
  all) cannot be transacted.
* **liquidity / partial fills** — a single order may take at most
  ``participation_rate`` of a bar's volume (a coarse market-impact proxy).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketRules:
    """Toggles + parameters for A-share trading realism (all default to ON)."""

    t_plus_1: bool = True
    enforce_price_limits: bool = True
    enforce_suspension: bool = True
    # Max fraction of a bar's volume a single order may fill; 0 disables the cap.
    participation_rate: float = 0.10
    # Limit band used when the board can't be inferred from the code (e.g. ST,
    # or non-numeric test symbols). Real ST is ±5% but isn't detectable here.
    default_limit_pct: float = 0.10


def limit_pct(symbol: str, default: float = 0.10) -> float:
    """Daily price-limit fraction for ``symbol``, inferred from its code prefix.

    * STAR Market (``688``/``689``) and ChiNext (``300``/``301``) → **0.20**
    * Beijing Stock Exchange (``4*`` / ``8*`` / ``92*``) → **0.30**
    * Shanghai/Shenzhen main boards → **0.10**
    * Non-numeric symbols (e.g. ``FAKE001``) or unknown → ``default``

    ST names trade at ±5% but can't be told apart from the code alone, so they
    fall back to ``default`` (0.10) — a documented limitation.
    """
    code = symbol.split(".")[0]
    if not code.isdigit() or len(code) < 3:
        return default
    p3 = code[:3]
    if p3 in {"688", "689", "300", "301"}:
        return 0.20
    if code[0] in {"4", "8"} or p3 == "920":
        return 0.30  # Beijing Stock Exchange
    return default  # main boards (and undetectable ST) → 0.10
