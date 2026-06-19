"""akshare-backed :class:`DataSource` for China A-share market data.

Wraps every network call with rate limiting + retries, normalises akshare's
Chinese-named columns into validated :class:`Bar` objects, and converts A-share
quirks (volume in 手/lots → shares, trading-date → UTC). Malformed rows are
skipped (some data loss is acceptable) rather than aborting the symbol.

Only daily bars are implemented for now; recent/intraday data will come from QMT.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import logfire
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from super_trade.data import Bar, Interval
from super_trade.ingest.rate_limit import RateLimiter
from super_trade.sources.base import Adjust, DataSource, SymbolInfo

if TYPE_CHECKING:
    from tenacity import RetryCallState

# A-share daily volume from eastmoney is reported in 手 (1 lot = 100 shares).
SHARES_PER_LOT = 100

_AK_PERIOD: dict[Interval, str] = {Interval.DAY: "daily"}
_AK_ADJUST: dict[Adjust, str] = {
    Adjust.NONE: "",
    Adjust.QFQ: "qfq",
    Adjust.HFQ: "hfq",
}

# requests' network errors subclass OSError; these are the retryable failures.
_RETRYABLE: tuple[type[BaseException], ...] = (OSError, TimeoutError)


def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    logfire.warn(
        "akshare call failed, retrying (attempt {attempt})",
        attempt=state.attempt_number,
        error=str(exc),
    )


class AkshareSource(DataSource):
    """Fetch China A-share data via akshare, reliably."""

    def __init__(
        self,
        *,
        rate_limiter: RateLimiter | None = None,
        max_retries: int = 4,
        shares_per_lot: int = SHARES_PER_LOT,
    ) -> None:
        self._rate_limiter = rate_limiter or RateLimiter(min_interval=0.5)
        self._max_retries = max_retries
        self._shares_per_lot = shares_per_lot
        self._ak: Any = None

    @property
    def _akshare(self) -> Any:
        """Lazily import akshare (heavy import; only paid on first use)."""
        if self._ak is None:
            import akshare as ak

            self._ak = ak
        return self._ak

    def _call(self, fn: Callable[[Any], Any]) -> Any:
        """Run an akshare call under the rate limiter, retrying transient errors."""

        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential_jitter(initial=1.0, max=30.0),
            retry=retry_if_exception_type(_RETRYABLE),
            before_sleep=_log_retry,
            reraise=True,
        )
        def _attempt() -> Any:
            self._rate_limiter.wait()
            return fn(self._akshare)

        return _attempt()

    def list_symbols(self) -> list[SymbolInfo]:
        df = self._call(lambda ak: ak.stock_info_a_code_name())
        out: list[SymbolInfo] = []
        for rec in df.to_dict("records"):
            code = str(rec.get("code") or rec.get("代码") or "").strip()
            name = str(rec.get("name") or rec.get("名称") or "").strip()
            if code:
                out.append(SymbolInfo(symbol=code, name=name))
        return out

    def fetch_bars(
        self,
        symbol: str,
        interval: Interval,
        start: datetime | None = None,
        end: datetime | None = None,
        adjust: Adjust = Adjust.HFQ,
    ) -> list[Bar]:
        period = _AK_PERIOD.get(interval)
        if period is None:
            raise NotImplementedError(
                f"akshare source only supports {list(_AK_PERIOD)} so far, "
                f"got {interval!r}"
            )
        start_date = start.strftime("%Y%m%d") if start else "19900101"
        end_date = end.strftime("%Y%m%d") if end else "20991231"
        df = self._call(
            lambda ak: ak.stock_zh_a_hist(
                symbol=symbol,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust=_AK_ADJUST[adjust],
            )
        )
        return self._to_bars(df, symbol, interval)

    def _to_bars(self, df: Any, symbol: str, interval: Interval) -> list[Bar]:
        if df is None or len(df) == 0:
            return []
        bars: list[Bar] = []
        skipped = 0
        for rec in df.to_dict("records"):
            try:
                bars.append(
                    Bar(
                        symbol=symbol,
                        interval=interval,
                        timestamp=_to_utc_date(rec["日期"]),
                        open=float(rec["开盘"]),
                        high=float(rec["最高"]),
                        low=float(rec["最低"]),
                        close=float(rec["收盘"]),
                        volume=round(float(rec["成交量"]) * self._shares_per_lot),
                    )
                )
            except Exception as exc:
                skipped += 1
                logfire.debug(
                    "skipping malformed row for {symbol}", symbol=symbol, error=str(exc)
                )
        if skipped:
            logfire.warn(
                "{symbol}: skipped {skipped} malformed rows",
                symbol=symbol,
                skipped=skipped,
            )
        return bars


def _to_utc_date(value: Any) -> datetime:
    """Normalise an akshare trading date (str/date/Timestamp) to UTC midnight."""
    if isinstance(value, datetime):
        d: Any = value
    elif hasattr(value, "year") and hasattr(value, "month"):  # date / pd.Timestamp
        d = value
    else:
        d = datetime.strptime(str(value)[:10], "%Y-%m-%d")
    return datetime(d.year, d.month, d.day, tzinfo=UTC)
