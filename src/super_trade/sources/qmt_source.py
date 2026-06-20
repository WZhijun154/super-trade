"""QMT (迅投 xtquant) :class:`DataSource` for China A-share market data.

QMT is an authenticated broker data link (via the MiniQMT terminal + the
``xtquant`` Python library), so it avoids akshare's scraping/WAF/IP problems and
provides accurate daily, minute, and tick data with proper adjustments.

Model: **download → query**. ``xtdata.download_history_data`` pulls history from
the broker into a local cache; ``get_market_data_ex`` then reads it (with
``dividend_type`` for adjustment). ``xtdata`` is imported lazily and only works on
a machine running MiniQMT — importing this module elsewhere is safe.

VERIFY ON A MiniQMT MACHINE (cannot be tested in CI/Linux):
* **Volume unit** — set ``shares_per_lot`` to match QMT's ``volume`` field (手/lots
  vs shares). Cross-check one bar against a known value before trusting it.
* **Bar timestamp semantics** — daily uses the date index; intraday uses the
  ``time`` epoch-ms field. Confirm the timezone/instant matches expectations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import logfire

from super_trade.data import Bar, Interval
from super_trade.sources.base import Adjust, DataSource, SymbolInfo

# QMT sector containing the full A-share universe.
_DEFAULT_SECTOR = "沪深A股"

_QMT_PERIOD: dict[Interval, str] = {
    Interval.MINUTE: "1m",
    Interval.FIVE_MINUTE: "5m",
    Interval.FIFTEEN_MINUTE: "15m",
    Interval.HOUR: "1h",
    Interval.DAY: "1d",
}
_DAILY_PERIODS = {"1d", "1w", "1mon"}

_QMT_ADJUST: dict[Adjust, str] = {
    Adjust.NONE: "none",
    Adjust.QFQ: "front",
    Adjust.HFQ: "back",
}


def to_qmt_symbol(symbol: str) -> str:
    """Map a bare 6-digit A-share code to QMT's ``CODE.EXCHANGE`` form.

    ``"600519"`` -> ``"600519.SH"``, ``"000001"`` -> ``"000001.SZ"``,
    ``"830799"`` -> ``"830799.BJ"``. Already-suffixed codes pass through.
    """
    code = symbol.strip()
    if "." in code:
        return code.upper()
    first = code[:1]
    if first in "69":  # 6xx/688 Shanghai, 9xx SH B-share
        suffix = "SH"
    elif first in "0123":  # 000/001/002/003/30x Shenzhen, 2xx SZ B-share
        suffix = "SZ"
    elif first in "48":  # 4xxxxx/8xxxxx Beijing
        suffix = "BJ"
    else:
        suffix = "SH"
    return f"{code}.{suffix}"


def from_qmt_symbol(code: str) -> str:
    """Strip QMT's exchange suffix: ``"600519.SH"`` -> ``"600519"``."""
    return code.split(".", 1)[0]


class QmtSource(DataSource):
    """Fetch China A-share data via QMT/xtquant (broker-grade, no scraping)."""

    def __init__(
        self,
        *,
        connect: bool = True,
        sector: str = _DEFAULT_SECTOR,
        shares_per_lot: int = 1,
    ) -> None:
        self._connect = connect
        self._sector = sector
        self._shares_per_lot = shares_per_lot
        self._xt: Any = None

    @property
    def _xtdata(self) -> Any:
        """Lazily import xtquant.xtdata and connect to the local MiniQMT terminal."""
        if self._xt is None:
            from xtquant import xtdata

            if self._connect:
                xtdata.connect()
            self._xt = xtdata
        return self._xt

    def list_symbols(self) -> list[SymbolInfo]:
        xt = self._xtdata
        out: list[SymbolInfo] = []
        for code in xt.get_stock_list_in_sector(self._sector):
            name = ""
            try:
                detail = xt.get_instrument_detail(code)
                if detail:
                    name = detail.get("InstrumentName", "") or ""
            except Exception as exc:
                logfire.debug("no detail for {code}", code=code, error=str(exc))
            out.append(SymbolInfo(symbol=from_qmt_symbol(code), name=name))
        return out

    def fetch_bars(
        self,
        symbol: str,
        interval: Interval,
        start: datetime | None = None,
        end: datetime | None = None,
        adjust: Adjust = Adjust.HFQ,
    ) -> list[Bar]:
        period = _QMT_PERIOD.get(interval)
        if period is None:
            raise NotImplementedError(f"QMT source does not support {interval!r}")
        code = to_qmt_symbol(symbol)
        fmt = "%Y%m%d" if period in _DAILY_PERIODS else "%Y%m%d%H%M%S"
        start_str = start.strftime(fmt) if start else ""
        end_str = end.strftime(fmt) if end else ""

        xt = self._xtdata
        # Ensure the local cache covers the range, then read it back.
        xt.download_history_data(
            code, period=period, start_time=start_str, end_time=end_str
        )
        data = xt.get_market_data_ex(
            ["time", "open", "high", "low", "close", "volume"],
            [code],
            period=period,
            start_time=start_str,
            end_time=end_str,
            count=-1,
            dividend_type=_QMT_ADJUST[adjust],
            fill_data=False,
        )
        return self._to_bars(data.get(code), symbol, interval, period)

    def _to_bars(
        self, df: Any, symbol: str, interval: Interval, period: str
    ) -> list[Bar]:
        if df is None or len(df) == 0:
            return []
        is_daily = period in _DAILY_PERIODS
        bars: list[Bar] = []
        skipped = 0
        for idx, row in df.iterrows():
            try:
                if is_daily:
                    ts = _date_label_to_utc(str(idx))
                else:
                    ts = datetime.fromtimestamp(int(row["time"]) / 1000, tz=UTC)
                bars.append(
                    Bar(
                        symbol=symbol,
                        interval=interval,
                        timestamp=ts,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=round(float(row["volume"]) * self._shares_per_lot),
                    )
                )
            except Exception as exc:
                skipped += 1
                logfire.debug(
                    "skipping malformed QMT row for {symbol}",
                    symbol=symbol,
                    error=str(exc),
                )
        if skipped:
            logfire.warn(
                "{symbol}: skipped {skipped} malformed QMT rows",
                symbol=symbol,
                skipped=skipped,
            )
        return bars


def _date_label_to_utc(label: str) -> datetime:
    """Parse a QMT daily index label (``YYYYMMDD``) to UTC midnight."""
    d = datetime.strptime(label[:8], "%Y%m%d")
    return datetime(d.year, d.month, d.day, tzinfo=UTC)
