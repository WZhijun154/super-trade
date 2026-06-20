"""Daily trading report.

Summarizes a session's fills and the resulting account into a Markdown report.
Designed to be generated at market close (e.g. from a scheduled job) and saved or
sent. Pure and side-effect-free: hand it the day's fills + broker + last prices.
"""

from __future__ import annotations

from .broker import Broker, Fill, Side


def daily_report(
    broker: Broker,
    fills: list[Fill],
    prices: dict[str, float],
    *,
    date_label: str = "",
) -> str:
    """Build a Markdown summary of the day's activity and current positions."""
    buys = [f for f in fills if f.side == Side.BUY]
    sells = [f for f in fills if f.side == Side.SELL]
    total_cost = sum(f.cost for f in fills)
    cash = broker.cash()
    positions = broker.positions()
    market_value = sum(
        pos.shares * prices.get(sym, pos.avg_price) for sym, pos in positions.items()
    )
    equity = cash + market_value

    lines = [
        f"# Daily report {date_label}".rstrip(),
        "",
        "## Summary",
        f"- equity: CNY {equity:,.2f}",
        f"- cash: CNY {cash:,.2f}  ·  positions: CNY {market_value:,.2f}",
        f"- fills: {len(fills)}  ({len(buys)} buys, {len(sells)} sells)",
        f"- transaction costs: CNY {total_cost:,.2f}",
        f"- open positions: {len(positions)}",
        "",
        "## Trades",
    ]
    if fills:
        lines.append("| symbol | side | shares | price | cost | reason |")
        lines.append("|---|---|---|---|---|---|")
        for f in fills:
            lines.append(
                f"| {f.symbol} | {f.side.value} | {f.shares} | "
                f"{f.price:.2f} | {f.cost:.2f} | {f.reason} |"
            )
    else:
        lines.append("_no trades today_")

    lines += ["", "## Positions"]
    if positions:
        lines.append("| symbol | shares | avg price | last | unreal. P&L |")
        lines.append("|---|---|---|---|---|")
        for sym, pos in sorted(positions.items()):
            last = prices.get(sym, pos.avg_price)
            pnl = (last - pos.avg_price) * pos.shares
            lines.append(
                f"| {sym} | {pos.shares} | {pos.avg_price:.2f} | "
                f"{last:.2f} | {pnl:+,.2f} |"
            )
    else:
        lines.append("_flat — no open positions_")

    return "\n".join(lines) + "\n"
