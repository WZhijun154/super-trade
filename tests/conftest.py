"""Shared pytest fixtures.

Two test tiers:
* **unit** — run against :class:`FakeStore`, no external services. Always run.
* **integration** (``@pytest.mark.integration``) — run against a real ClickHouse,
  using a dedicated ``super_trade_test`` database that is dropped afterwards so the
  real ``super_trade`` data (which backtests read) is never touched. Auto-skipped
  when no server is reachable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from factories import make_bars
from fakes import FakeStore

from super_trade.data import Bar, ClickHouseConfig, ClickHouseStore


@pytest.fixture(scope="session", autouse=True)
def _logfire_offline() -> None:
    """Keep Logfire silent and offline during tests."""
    import logfire

    logfire.configure(send_to_logfire=False, console=False)


@pytest.fixture
def synthetic_bars() -> Callable[..., list[Bar]]:
    """The mock-data factory. TEST ONLY — never use this data in a backtest."""
    return make_bars


@pytest.fixture
def fake_store() -> Iterator[FakeStore]:
    store = FakeStore()
    store.init_schema()
    yield store
    store.close()


@pytest.fixture(scope="session")
def clickhouse_store() -> Iterator[ClickHouseStore]:
    # Isolated test database — keeps mock rows out of the real `super_trade` DB.
    config = ClickHouseConfig(database="super_trade_test")
    store = ClickHouseStore(config)
    try:
        store.client.command("SELECT 1")
    except Exception as exc:
        pytest.skip(f"ClickHouse not reachable for integration tests: {exc}")
    store.init_schema()
    yield store
    store.client.command(f"DROP DATABASE IF EXISTS {config.database} SYNC")
    store.close()


@pytest.fixture
def clean_clickhouse(clickhouse_store: ClickHouseStore) -> ClickHouseStore:
    """A ClickHouse store with an empty `bars` table for each test."""
    db = clickhouse_store._config.database
    clickhouse_store.client.command(f"TRUNCATE TABLE IF EXISTS {db}.bars")
    return clickhouse_store
