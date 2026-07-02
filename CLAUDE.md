# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`super-trade` is a quantitative trading platform for the **China A-share** market, for a
personal/retail quant. It spans the full research loop, each layer behind an interface so
backends are swappable and testable:

```
acquire (sources) → store (data) → orchestrate (ingest)
                                        ↓
            metrics → backtest → execution → viz → dashboard
```

Plain Polars DataFrames flow downstream between layers. Data strategy: **akshare** for bulk free
history (scraped); **QMT** (`xtquant`) for accurate recent/intraday/precise data and live trading
— both behind the same `DataSource` / `Broker` interfaces.

## Architecture (big picture)

```
src/super_trade/
├── data/         STORAGE — DataStore (ABC) + ClickHouseStore; Bar model, Interval, BAR_COLUMNS
├── sources/      ACQUISITION — DataSource (ABC), Adjust enum; AkshareSource, QmtSource
├── ingest/       PIPELINE — RateLimiter + DailyBackfill (cache-aware, idempotent) + main()
├── metrics/      INDICATORS — Polars-expression metrics by family + scalar summary stats
├── backtest/     BACKTEST — Strategy (ABC), VectorizedEngine, CostModel, BacktestResult
├── execution/    EXECUTION — Broker (Sim/QMT), ExecutionEngine, RiskManager, EventDrivenBacktest
├── viz/          CHARTS — pure Plotly figure builders (DataFrame -> go.Figure)
└── observability.py  configure_logfire()
dashboard/        Streamlit app (presentation only)
website/          Docusaurus 3 docs site (pnpm) -> GitHub Pages
```

Key design decisions (the *why*):

- **Interfaces, not implementations.** `DataStore`, `DataSource`, and `Broker` are abstract;
  concrete backends (ClickHouse, akshare/QMT, Sim/QMT) are swappable and testable.
- **ClickHouse is the cache.** `DailyBackfill` reads `store.latest_timestamp(symbol)` and fetches
  only the missing tail. The `bars` table is a `ReplacingMergeTree` ordered by
  `(symbol, interval, timestamp)` → re-ingesting replaces, not duplicates; reads use `FINAL`.
- **v1 stores `hfq` (backward-adjusted) daily bars only.** hfq is stable over time (right for
  backtesting); qfq drifts. No `adjust` dimension in the schema yet — adding raw/qfq is a schema
  migration (add `adjust` to the `ORDER BY` key), not mixing adjustments into the same keys.
- **Reliability lives in the source.** `AkshareSource` wraps each network call with a
  `RateLimiter` + `tenacity` retries; `DailyBackfill` stays simple (loop + cache + per-symbol
  failure isolation via `BackfillReport`).
- **Metrics are pure Polars expressions.** Each returns a `pl.Expr`, composing into
  `df.with_columns(...)` and panels via `.over("symbol")`. Per-bar indicators vs scalar summary
  stats (`SCALAR_METRICS`); multi-output ones return structs (`STRUCT_METRICS`, `.unnest()`).
- **Backtest reuses everything below it.** Strategies are exprs over `metrics`; stats come from
  `metrics.summary`; charts from `viz`. The vectorized engine lags positions one bar (no
  lookahead) and charges A-share costs (commission, stamp tax sell-only, slippage).
- **Backtest ↔ live share one code path.** The same `Strategy` + `RiskManager` drive a `SimBroker`
  (dry-run / `EventDrivenBacktest`) or a `QmtBroker` (live, **QMT simulation account**). Only the
  broker (and the clock: historical bars vs a 10s scan) differs.
- **Two backtest tiers.** *Vectorized* (`backtest/`) = fast signal research, but can't model
  path-dependent things. *Event-driven* (`execution/EventDrivenBacktest`) replays bar-by-bar
  through `SimBroker` → models stop-loss, real cash/lots/per-name sizing.

### akshare / QMT gotchas (encoded in the sources)

- **eastmoney blocks datacenter / non-mainland IPs.** `stock_zh_a_hist` (East Money) completes TLS
  then drops the request from HK/cloud IPs — it's WAF/IP, not UA or fingerprint. Works from a
  mainland-CN IP. Also per-IP throttled: keep `RateLimiter(min_interval)` ≥ 1–2s; multi-node only
  helps with **distinct egress IPs**. (Sina endpoints like `stock_zh_a_daily` use a different
  host and may work when eastmoney doesn't — but eastmoney/Sina `hfq` use different bases; don't
  mix sources in one series.)
- **Normalization**: akshare columns are Chinese; volume in 手 (lots) → ×100 to shares; dates →
  UTC midnight; malformed rows skipped. **QMT** uses `code.SH/.SZ/.BJ` symbols and `download →
  query`; `xtquant` is imported lazily and must be verified on a MiniQMT box (volume unit, time
  semantics).

## Commands

```bash
uv sync                                   # venv from the lockfile
uv add <pkg>            / uv add --dev <pkg>   # deps (keeps uv.lock in sync — don't hand-edit)

uv run python -m super_trade.ingest.backfill   # daily A-share backfill (reads .env)
uv run streamlit run dashboard/app.py          # the explorer dashboard (localhost:8501)

# Lint/format (or the /ruff-fix skill for a clean-to-green pass incl. manual fixes)
uv run ruff format . && uv run ruff check --fix .
uv run ruff check .                       # CI check

# Type-check (strict mypy over src/ + tests/; config in pyproject.toml)
uv run mypy                                # reads [tool.mypy] files=[...]; no path arg

# Tests
uv run pytest -m "not integration"        # unit tier — fast, no services (default for dev/CI)
uv run pytest                             # + integration tier (needs ClickHouse)
uv run pytest tests/test_x.py::test_name  # single test

# Docs site (website/ — Docusaurus, pnpm; auto-deploys to GitHub Pages on push to main)
cd website && pnpm install && pnpm build  # pnpm start = live dev; pnpm serve = preview build
```

## Infrastructure

- **ClickHouse** via Docker (`docker compose up`); HTTP on host port **8124** (`"8124:8123"`),
  used through `clickhouse-connect`.
- **Secrets** in a gitignored `.env` (template `.env.example`). `ClickHouseConfig` is a
  `pydantic-settings` model reading `CLICKHOUSE_*`. Never hardcode/commit credentials.
- **Observability** is [Logfire](https://logfire.pydantic.dev/). Call `configure_logfire()` at
  process entry; ships only when `LOGFIRE_TOKEN` is set. **Use logfire, not stdlib `logging`.**
- **Docs** deploy to **public** GitHub Pages (the repo is public; a private personal-account Pages
  site isn't possible on Free). Don't put secrets in `website/`.

## Conventions

- **Mock data is TEST-ONLY**, under `tests/` (`factories.py`, `fakes.py`) — *not* part of the
  package, so backtest/production code can't import it. **Backtests/execution read real data from
  a `DataStore`; never synthetic.** Structural — keep it that way.
- **Two test tiers.** Unit (against `FakeStore` / `SimBroker`) — fast, no services. Integration
  (`@pytest.mark.integration`) — real ClickHouse in an isolated `super_trade_test` db, dropped
  after, auto-skipped if unreachable. There's also a `super_trade_sandbox` db with realistic
  synthetic data (`scripts/seed_sandbox.py`) for the dashboard/demos — **not** for backtests.
- **Execution safety.** `ExecutionEngine` defaults to `dry_run=True` (logs, sends nothing). Live
  goes only to a **QMT simulation account**; keep `RiskManager` limits on. The halt blocks new
  buys only — exits/stop-losses always go through.
- **Code style** (ruff, config in `pyproject.toml`): type hints everywhere, modern generics
  (`list[int]`, `X | None`), `snake_case`/`PascalCase`/`UPPER_SNAKE`, docstrings on public
  modules/classes/functions, double quotes, 88-col lines. `plotly`/`streamlit` are core deps.

## Orchestration note

The ingest pipeline is a linear loop, not a DAG — a scheduled run of
`super_trade.ingest.backfill` is enough. If real orchestration is needed later, use
**Prefect/Dagster** or the in-house **astraq** task queue — **not** pydantic-graph (a
state-machine lib for agent flows, not ETL).
