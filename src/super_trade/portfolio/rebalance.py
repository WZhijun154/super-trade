"""Periodic rebalance — re-select and re-allocate on a schedule.

The selection + allocation in :mod:`super_trade.selection` / this package are
*point-in-time*. A real portfolio re-runs them periodically: every few weeks it
re-screens the universe and re-sizes the book. :func:`periodic_schedule` precomputes
that — at each rebalance date it builds a feature snapshot **as of that date**
(causal — only past bars), selects, and allocates — and returns:

* the **union universe** (every name selected at any rebalance), so the backtest
  loads bars/signals for all of them; and
* a date-sorted **weight schedule** ``[(effective_date, {symbol: weight})]`` that
  ``EventDrivenBacktest(weight_schedule=…)`` consumes. A name dropped at a rebalance
  simply gets weight 0 from then on, and the engine scales it out.

It runs *before* the backtest (one selection pass per rebalance date), keeping the
event loop itself free of selection logic.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import polars as pl

from super_trade.data import DataStore, Interval
from super_trade.portfolio.allocator import Allocator
from super_trade.selection import Selector, build_features


def _trading_dates(
    store: DataStore, symbols: list[str], interval: Interval
) -> list[date]:
    """Sorted unique calendar of dates that any symbol has a bar on."""
    seen: set[date] = set()
    for symbol in symbols:
        bars = store.read_bars(symbol, interval)
        seen.update(ts.date() for ts in bars["timestamp"].to_list())
    return sorted(seen)


def periodic_schedule(
    store: DataStore,
    selector: Selector,
    allocator: Allocator,
    *,
    symbols: list[str] | None = None,
    interval: Interval = Interval.DAY,
    every: int = 21,
    lookback: int = 60,
    fundamentals: pl.DataFrame | None = None,
) -> tuple[list[str], list[tuple[date, dict[str, float]]]]:
    """Build the (union universe, weight schedule) for a periodic rebalance.

    Rebalances on every ``every``-th trading day once ``lookback`` days of history
    exist. At each, features are computed from bars **strictly before** that date
    (causal), so the new weights drive trading from that day's open with no lookahead.

    Args:
        store: Source of bars.
        selector: The selection pipeline (filters + score → universe).
        allocator: Sizes the selected names into weights.
        symbols: Candidate pool; ``None`` = every symbol at ``interval``.
        interval: Bar interval features/calendar are measured on.
        every: Rebalance period, in trading days (21 ≈ monthly for daily bars).
        lookback: Trailing bars each feature snapshot uses (and the warm-up before
            the first rebalance).
        fundamentals: Optional per-symbol fundamentals frame (see ``build_features``).
            Static here — time-varying fundamentals are future work.

    Returns:
        ``(universe, schedule)`` — the union of all selected symbols, and a
        date-sorted ``[(effective_date, {symbol: weight})]`` schedule.
    """
    if symbols is None:
        symbols = store.list_symbols(interval)
    calendar = _trading_dates(store, symbols, interval)

    universe: set[str] = set()
    schedule: list[tuple[date, dict[str, float]]] = []
    for d in calendar[lookback::every]:
        # end-exclusive at midnight → use only bars strictly before day d (causal).
        asof = datetime(d.year, d.month, d.day, tzinfo=UTC)
        feats = build_features(
            store,
            symbols,
            interval=interval,
            asof=asof,
            lookback=lookback,
            fundamentals=fundamentals,
        )
        picks = selector.select(feats)
        if not picks:
            schedule.append((d, {}))  # nothing qualifies → flat this period
            continue
        weights = allocator.weights(feats.filter(pl.col("symbol").is_in(picks)))
        schedule.append((d, weights))
        universe.update(weights)

    return sorted(universe), schedule
