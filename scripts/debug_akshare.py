"""Manual debug entry point for AkshareSource (East Money `stock_zh_a_hist`).

Run under the debugger (see .vscode/launch.json → "Debug AkshareSource"). Set
breakpoints in src/super_trade/sources/akshare_source.py — e.g. inside `fetch_bars`
or `_to_bars` — and step into the `stock_zh_a_hist` call.

Note: `stock_zh_a_hist` hits East Money, which is reachable from China/Aliyun but
blocks some non-CN IPs (you'll get RemoteDisconnected there).
"""

from __future__ import annotations

from datetime import UTC, datetime

from super_trade.data import Interval
from super_trade.ingest import RateLimiter
from super_trade.sources import Adjust, AkshareSource


def main() -> None:
    source = AkshareSource(rate_limiter=RateLimiter(min_interval=1.0))
    bars = source.fetch_bars(
        "600519",
        Interval.DAY,
        start=datetime(2024, 1, 2, tzinfo=UTC),
        end=datetime(2024, 1, 15, tzinfo=UTC),
        adjust=Adjust.HFQ,
    )
    print(f"fetched {len(bars)} bars")
    for bar in bars[:5]:
        print(bar)


if __name__ == "__main__":
    main()
