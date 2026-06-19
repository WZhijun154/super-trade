# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`super-trade` is a quantitative trading data platform (early stage). Current focus: reliably
ingesting **China A-share** market data into ClickHouse for backtesting and research. The
initial trader/user is a personal/retail quant.

Data strategy: **akshare** provides the bulk of historical data (free, scraped from
eastmoney/Sina); **QMT** will later provide recent/intraday/precise data. The ingestion layer is
source-agnostic so QMT slots in behind the same interface.

## Architecture (big picture)

Three layers, each behind an interface so backends are swappable and testable:

```
src/super_trade/
├── data/            STORAGE — where bars live
│   ├── models.py        Bar (Pydantic, validated OHLCV), Interval enum, BAR_COLUMNS
│   ├── store.py         DataStore (ABC): write_bars/read_bars/latest_timestamp/list_symbols
│   └── clickhouse_store.py  ClickHouseStore + ClickHouseConfig (env-driven)
├── sources/         ACQUISITION — where bars come from
│   ├── base.py          DataSource (ABC), SymbolInfo, Adjust enum (none/qfq/hfq)
│   └── akshare_source.py    AkshareSource: throttled+retried fetch → normalized Bars
├── ingest/          PIPELINE — orchestration
│   ├── rate_limit.py    RateLimiter (per-process request spacing)
│   └── backfill.py      DailyBackfill (cache-aware, idempotent) + `main()`
└── observability.py  configure_logfire()
```

Key design decisions (the *why*, since it's not obvious from code):

- **Storage and acquisition are separate abstractions.** `DataStore` and `DataSource` never
  know about each other; `DailyBackfill` wires them together. Add a new source (QMT) or backend
  without touching the rest.
- **ClickHouse is the cache.** `DailyBackfill` reads `store.latest_timestamp(symbol)` and fetches
  only the missing tail (plus a short lookback to recapture corrections). No external checkpoint
  store needed.
- **Idempotent writes.** The `bars` table is a `ReplacingMergeTree` ordered by
  `(symbol, interval, timestamp)`; re-ingesting overlapping ranges replaces rather than
  duplicates, so interrupted/repeated runs are safe. Reads use `FINAL` to dedup at query time.
- **Reliability lives in the source.** `AkshareSource` wraps every network call with a
  `RateLimiter` + `tenacity` retries; the orchestrator stays simple (loop + cache + per-symbol
  failure isolation via `BackfillReport`).
- **v1 stores `hfq` (backward-adjusted) daily bars only.** hfq is stable over time (right for
  backtesting); qfq drifts. There is intentionally **no `adjust` dimension in the schema yet** —
  the table holds one adjustment series. If raw/qfq are ever needed, add `adjust` to the
  `ORDER BY` key (a schema migration) rather than writing mixed adjustments into the same keys.

### akshare gotchas (encoded in `AkshareSource`)

- **Per-IP throttling.** eastmoney drops bursts/large requests (`RemoteDisconnected`). akshare
  itself has no limit; the source does. Keep `RateLimiter(min_interval)` ≥ 1–2s in production.
  Multi-node scaling only helps with **distinct egress IPs** (see git history / chat for the
  NAT/EIP discussion).
- **Normalization**: columns are Chinese; volume is in 手 (lots) → multiplied by `SHARES_PER_LOT`
  (100) to get shares; trading dates → UTC midnight. Malformed rows are skipped (some data loss
  is acceptable), not fatal.
- **Daily only** so far (`stock_zh_a_hist`). Minute/tick history from akshare is shallow — that's
  QMT's job later.

## Commands

```bash
uv sync                                   # set up/refresh the venv from the lockfile
uv add <pkg>            / uv add --dev <pkg>   # add deps (keeps uv.lock in sync — don't hand-edit)
uv run <cmd>                              # run inside the project venv

# Run the daily A-share backfill (full universe; reads .env for ClickHouse)
uv run python -m super_trade.ingest.backfill

# Lint/format (or use the /ruff-fix skill for a clean-to-green pass incl. manual fixes)
uv run ruff format . && uv run ruff check --fix .
uv run ruff check .                       # CI check

# Tests
uv run pytest -m "not integration"        # unit tier — fast, no services (default for dev/CI)
uv run pytest                             # + integration tier (needs ClickHouse running)
uv run pytest tests/test_x.py::test_name  # single test
```

## Infrastructure

- **ClickHouse** runs via Docker (`docker compose up`; see the compose file). HTTP interface is
  what the app uses (`clickhouse-connect`), mapped to host port **8124** (`"8124:8123"`).
- **Secrets** live in a gitignored `.env` (template: `.env.example`). `ClickHouseConfig` is a
  `pydantic-settings` model reading `CLICKHOUSE_*`. Never hardcode credentials; never commit `.env`.
- **Observability** is [Logfire](https://logfire.pydantic.dev/). Call `configure_logfire()` at
  process entry (done in `backfill.main()`); it only ships data when `LOGFIRE_TOKEN` is set, so
  local/CI/offline runs work without setup. **Use logfire, not stdlib `logging`**, in app code.

## Testing conventions

- **Two tiers.** Unit tests run against `FakeStore` (in-memory `DataStore`) — fast, no services.
  Integration tests (`@pytest.mark.integration`) run against a real ClickHouse in an isolated
  `super_trade_test` database that is dropped afterward, and auto-skip if no server is reachable.
- **Mock data is TEST-ONLY and lives under `tests/`** (`factories.py`, `fakes.py`). It is *not*
  part of the `super_trade` package, so backtest/production code cannot import it. **Backtests
  must read real data from a `DataStore` — never synthetic data.** This separation is structural;
  keep it that way.

## Code style

Enforced by [`ruff`](https://docs.astral.sh/ruff/) (config in `pyproject.toml`). Always run
`ruff format` + `ruff check --fix` before considering a change done — do not hand-format.
Conventions ruff can't fully enforce:

- **Type hints** on all signatures; modern builtin generics (`list[int]`, `X | None`), not
  `typing.List`/`Optional` (py312 target).
- **Naming**: `snake_case` / `PascalCase` / `UPPER_SNAKE`. **Docstrings** on public modules,
  classes, functions (first line = one-sentence summary). **Double quotes**, **88-col** lines.
- Prefer `pathlib`, f-strings, and Pydantic/dataclasses over ad-hoc dicts for structured data.

## Orchestration note

The current pipeline is a linear loop, not a DAG — a plain scheduled run of
`super_trade.ingest.backfill` is sufficient. If real orchestration is needed later (scheduling,
parallel fan-out, run history), use **Prefect/Dagster** or the in-house **astraq** task queue —
**not** pydantic-graph (which is a state-machine lib for agent flows, not an ETL orchestrator).
