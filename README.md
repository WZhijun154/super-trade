# super-trade

A quantitative trading platform for the **China A-share** market, built for a
personal/retail quant. It spans the full research loop — acquire data, store it,
compute indicators, backtest strategies, and run them (dry-run or live on a QMT
simulation account) — with every layer behind an interface so backends are
swappable and testable.

📖 **Docs:** <https://wzhijun154.github.io/super-trade/>

---

## What it is

```
acquire (sources) → store (data) → orchestrate (ingest)
                                        ↓
     selection → metrics → backtest → execution → viz / foxglove → dashboard
```

Plain [Polars](https://pola.rs/) DataFrames flow downstream between layers. The
data strategy uses two backends behind the same interfaces:

- **akshare** — bulk free history (scraped) for backtesting.
- **QMT** (`xtquant`) — accurate recent/intraday/precise data and live trading.

## Architecture

Each package is one layer of the pipeline; concrete backends sit behind abstract
interfaces (`DataStore`, `DataSource`, `Broker`).

| Package | Layer | What it does |
|---|---|---|
| `data/` | **storage** | `DataStore` (ABC) + `ClickHouseStore`; the `Bar` model, `Interval`, resampling. ClickHouse is the cache. |
| `sources/` | **acquisition** | `DataSource` (ABC), `Adjust` enum; `AkshareSource`, `QmtSource`. Reliability (rate limiting, retries) lives here. |
| `ingest/` | **pipeline** | `RateLimiter` + cache-aware, idempotent `DailyBackfill` — fetches only the missing tail per symbol. |
| `selection/` | **stock selection** | Composable `filters` + `scorers` → a `Selector` that ranks a feature cross-section down to a tradeable universe. |
| `metrics/` | **indicators** | Pure Polars-expression metrics by family (trend, momentum, volatility, volume, returns) + scalar summary stats. |
| `backtest/` | **backtest (vectorized)** | `Strategy` (ABC), `VectorizedEngine`, `CostModel`, `BacktestResult`. Fast signal research, no lookahead, A-share costs. |
| `portfolio/` | **allocation** | `Allocator`s (`EqualWeight`, `InverseVol`, …) that size the selected names against each other. |
| `execution/` | **execution (event-driven / live)** | `Broker` (Sim/QMT), `ExecutionEngine`, `RiskManager`, `EventDrivenBacktest`. Models stop-loss, real cash/lots. |
| `runner/` | **large-scale backtesting** | `RunSpec` (a run as data) + `grid()`; a `Runner` fans specs out and reduces each to a stats row. Backends: `SimpleRunner`, `MultiProcessRunner`, `RayRunner` (k8s/k3s). |
| `viz/` | **charts** | Pure Plotly figure builders (`DataFrame -> go.Figure`). |
| `foxglove/` | **telemetry** | Export a backtest to `.mcap`, or stream it live over WebSocket, for the Foxglove "Trade Cockpit" panel. |
| `observability.py` | | Logfire configuration. |
| `dashboard/` | **presentation** | Streamlit explorer app. |
| `website/` | **docs** | Docusaurus 3 site → GitHub Pages. |

### Key design decisions (the *why*)

- **Interfaces, not implementations.** Storage, sources, and brokers are abstract;
  backends (ClickHouse, akshare/QMT, Sim/QMT) are swappable and unit-testable.
- **ClickHouse is the cache.** The `bars` table is a `ReplacingMergeTree` ordered by
  `(symbol, interval, timestamp)` → re-ingesting replaces rather than duplicates.
  `DailyBackfill` reads the latest stored timestamp and fetches only the tail.
- **v1 stores `hfq` (backward-adjusted) daily bars.** hfq is stable over time (right
  for backtesting); qfq drifts. Adding raw/qfq is a schema migration, not a mix.
- **Metrics are pure Polars expressions.** Each returns a `pl.Expr` that composes into
  `df.with_columns(...)` and panels via `.over("symbol")`.
- **Backtest reuses everything below it.** Strategies are exprs over `metrics`; stats
  come from `metrics.summary`; charts from `viz`.
- **Backtest ↔ live share one code path.** The same `Strategy` + `RiskManager` drive a
  `SimBroker` (dry-run) or a `QmtBroker` (live, on a QMT **simulation** account). Only
  the broker and the clock differ.
- **Two backtest tiers.** *Vectorized* (`backtest/`) = fast signal research. *Event-driven*
  (`execution/EventDrivenBacktest`) replays bar-by-bar through `SimBroker` to model
  path-dependent behaviour like stop-loss and real per-name sizing.

## Quickstart

**Prerequisites:** [uv](https://docs.astral.sh/uv/), Docker (for ClickHouse), Python ≥ 3.12.

```bash
# 1. Install dependencies from the lockfile
uv sync

# 2. Start ClickHouse (HTTP on host port 8124)
docker compose up -d

# 3. Configure secrets
cp .env.example .env      # then fill in CLICKHOUSE_* values

# 4. Backfill daily A-share history into ClickHouse
uv run python -m super_trade.ingest.backfill

# 5. Explore in the dashboard
uv run streamlit run dashboard/app.py     # http://localhost:8501
```

> **Note on akshare:** the East Money endpoint blocks datacenter / non-mainland IPs
> (WAF/IP-based), so bulk backfill works reliably only from a **mainland-CN IP**.

## Usage

Compute indicators as composable Polars expressions:

```python
import polars as pl
from super_trade import metrics as m
from super_trade.data import Interval

df = store.read_bars("600519", Interval.DAY)
df = df.with_columns(
    m.sma("close", 20).alias("sma_20"),
    m.rsi("close", 14).alias("rsi_14"),
)
df = df.with_columns(m.macd().alias("macd")).unnest("macd")  # multi-output → unnest
```

Run a vectorized backtest:

```python
from super_trade.backtest import VectorizedEngine, SmaCross

bars = store.read_bars("600519", Interval.DAY)
result = VectorizedEngine().run(bars, SmaCross(10, 30))
print(result.stats())
result.equity_curve().show()
```

Replay the same strategy bar-by-bar through the event-driven engine (models
stop-loss, real cash/lots) and stream it to Foxglove:

```python
from super_trade.execution import EventDrivenBacktest, RiskManager
from super_trade.foxglove import export_mcap

result = EventDrivenBacktest(store, SmaCross(10, 30), universe=["600519"]).run()
export_mcap(result, "run.mcap")   # scrub the run in Foxglove's Trade Cockpit
```

Sweep a parameter grid — the runner fans independent runs out and reduces each to a
comparable stats row. Swap `SimpleRunner` for `MultiProcessRunner()` to saturate a box,
or `RayRunner()` for a cluster; the code is otherwise identical:

```python
from super_trade.runner import SimpleRunner, grid

specs = grid("sma_cross", fast=[5, 10, 20], slow=[30, 60], universe=["600519"])
report = SimpleRunner().run(specs, store)
print(report.to_frame().sort("sharpe", descending=True))
best = report.best("sharpe")
```

Runnable end-to-end scripts live in [`examples/`](examples/README.md) (they read real
bars from the `super_trade_sandbox` database — seed it with
`uv run python scripts/seed_sandbox.py`).

## Development

```bash
# Format + lint
uv run ruff format . && uv run ruff check --fix .
uv run ruff check .                       # CI check

# Type-check (strict mypy over src/ + tests/)
uv run mypy

# Tests
uv run pytest -m "not integration"        # unit tier — fast, no services
uv run pytest                             # + integration tier (needs ClickHouse)
```

**Type checking.** mypy runs in `strict` mode (config in `pyproject.toml`) over
`src/` and `tests/`. Generated protobuf bindings are excluded, and third-party libs
without stubs (akshare, xtquant, clickhouse-connect, streamlit, …) are treated as
untyped rather than failing the run.

**Two test tiers.** Unit tests run against `FakeStore` / `SimBroker` — fast, no
services. Integration tests (`@pytest.mark.integration`) use a real ClickHouse in an
isolated `super_trade_test` database and auto-skip when it's unreachable.

**Mock data is test-only.** It lives under `tests/` and is *not* importable from the
package — backtests and execution always read real data from a `DataStore`.

## Infrastructure

- **ClickHouse** via Docker; HTTP exposed on host port **8124**, accessed through
  `clickhouse-connect`.
- **Secrets** in a gitignored `.env` (`CLICKHOUSE_*`, optional `LOGFIRE_TOKEN`); never
  hardcode or commit credentials.
- **Observability** via [Logfire](https://logfire.pydantic.dev/) — telemetry ships only
  when `LOGFIRE_TOKEN` is set, so local/CI/offline runs work with no setup.
- **Docs** deploy automatically to public GitHub Pages on push to `main`.

## Disclaimer

This is a personal research project, not investment advice. Live execution is limited
to a **QMT simulation account** by design; `ExecutionEngine` defaults to `dry_run=True`.
Trade at your own risk.
