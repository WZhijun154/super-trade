"""ClickHouse-backed :class:`DataStore` implementation.

Uses the official ``clickhouse-connect`` driver. Design choices that matter:

* **Bulk, columnar inserts** — never row-by-row ORM writes. This plays to
  ClickHouse's strengths.
* **``ReplacingMergeTree``** keyed by ``(symbol, interval, timestamp)`` and
  versioned by ``ingested_at`` — re-ingesting an overlapping range (e.g. after a
  split/dividend correction) replaces older rows on merge instead of duplicating.
* **Column codecs** (``DoubleDelta`` for timestamps, ``Gorilla`` for prices,
  ``T64`` for volume) give large compression wins on financial series.
* Reads default to ``FINAL`` so callers see deduplicated data even before a
  background merge has run.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import polars as pl
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import BAR_COLUMNS, Bar, Interval
from .store import DataStore

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client


class ClickHouseConfig(BaseSettings):
    """Connection settings for a ClickHouse server.

    Values are read (in precedence order) from explicit constructor args, then
    ``CLICKHOUSE_*`` environment variables, then a local ``.env`` file. Secrets
    therefore stay out of source — see ``.env.example``.
    """

    model_config = SettingsConfigDict(
        env_prefix="CLICKHOUSE_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    host: str = "localhost"
    port: int = 8123
    username: str = Field(default="default", alias="CLICKHOUSE_USER")
    password: str = ""
    database: str = "super_trade"
    secure: bool = False


_TABLE = "bars"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS {db}.{table}
(
    symbol      LowCardinality(String),
    interval    LowCardinality(String),
    timestamp   DateTime64(3, 'UTC') CODEC(DoubleDelta, ZSTD(1)),
    open        Float64 CODEC(Gorilla, ZSTD(1)),
    high        Float64 CODEC(Gorilla, ZSTD(1)),
    low         Float64 CODEC(Gorilla, ZSTD(1)),
    close       Float64 CODEC(Gorilla, ZSTD(1)),
    volume      UInt64  CODEC(T64, ZSTD(1)),
    ingested_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (symbol, interval, timestamp)
"""


class ClickHouseStore(DataStore):
    """Store market data in ClickHouse via ``clickhouse-connect``."""

    def __init__(
        self,
        config: ClickHouseConfig | None = None,
        *,
        dedup_on_read: bool = True,
    ) -> None:
        self._config = config or ClickHouseConfig()
        self._dedup_on_read = dedup_on_read
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        """Lazily-created, reused ClickHouse client."""
        if self._client is None:
            import clickhouse_connect

            # Connect to the server default DB; all table refs are qualified with
            # ``self._config.database`` so ``init_schema`` can create it first.
            self._client = clickhouse_connect.get_client(
                host=self._config.host,
                port=self._config.port,
                username=self._config.username,
                password=self._config.password,
                secure=self._config.secure,
            )
        return self._client

    def init_schema(self) -> None:
        db = self._config.database
        self.client.command(f"CREATE DATABASE IF NOT EXISTS {db}")
        self.client.command(_CREATE_TABLE.format(db=db, table=_TABLE))

    def write_bars(self, bars: Iterable[Bar] | pl.DataFrame) -> int:
        rows = self._to_rows(bars)
        if not rows:
            return 0
        self.client.insert(
            _TABLE,
            rows,
            column_names=list(BAR_COLUMNS),
            database=self._config.database,
        )
        return len(rows)

    def read_bars(
        self,
        symbol: str,
        interval: Interval,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pl.DataFrame:
        where = ["symbol = {symbol:String}", "interval = {interval:String}"]
        params: dict[str, object] = {"symbol": symbol, "interval": interval.value}
        if start is not None:
            where.append("timestamp >= {start:DateTime64(3)}")
            params["start"] = start
        if end is not None:
            where.append("timestamp < {end:DateTime64(3)}")
            params["end"] = end

        final = " FINAL" if self._dedup_on_read else ""
        columns = ", ".join(BAR_COLUMNS)
        query = (
            f"SELECT {columns} FROM {self._config.database}.{_TABLE}{final} "
            f"WHERE {' AND '.join(where)} ORDER BY timestamp"
        )
        table = self.client.query_arrow(query, parameters=params)
        # from_arrow on a multi-column Arrow table always yields a DataFrame.
        return pl.DataFrame(pl.from_arrow(table))

    def latest_timestamp(self, symbol: str, interval: Interval) -> datetime | None:
        query = (
            f"SELECT count() AS c, max(timestamp) AS m "
            f"FROM {self._config.database}.{_TABLE} "
            "WHERE symbol = {symbol:String} AND interval = {interval:String}"
        )
        result = self.client.query(
            query, parameters={"symbol": symbol, "interval": interval.value}
        )
        count, latest = result.result_rows[0]
        if not count:
            return None
        ts: datetime = latest
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts

    def list_symbols(self, interval: Interval | None = None) -> list[str]:
        params: dict[str, object] = {}
        clause = ""
        if interval is not None:
            clause = " WHERE interval = {interval:String}"
            params["interval"] = interval.value
        query = (
            f"SELECT DISTINCT symbol FROM {self._config.database}.{_TABLE}"
            f"{clause} ORDER BY symbol"
        )
        result = self.client.query(query, parameters=params)
        return [row[0] for row in result.result_rows]

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    @staticmethod
    def _to_rows(bars: Iterable[Bar] | pl.DataFrame) -> list[tuple[object, ...]]:
        """Normalise input into ClickHouse insert rows in ``BAR_COLUMNS`` order."""
        if isinstance(bars, pl.DataFrame):
            missing = set(BAR_COLUMNS) - set(bars.columns)
            if missing:
                raise ValueError(f"DataFrame missing columns: {sorted(missing)}")
            return bars.select(BAR_COLUMNS).rows()
        return [
            (
                b.symbol,
                b.interval.value,
                b.timestamp,
                b.open,
                b.high,
                b.low,
                b.close,
                b.volume,
            )
            for b in bars
        ]
