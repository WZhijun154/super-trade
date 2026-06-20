---
sidebar_position: 2
title: Getting started
---

# Getting started

## Prerequisites

- Python **3.12** and [`uv`](https://docs.astral.sh/uv/)
- Docker (for ClickHouse)

## Setup

```bash
uv sync                 # create the venv from uv.lock
cp .env.example .env    # then fill in CLICKHOUSE_* (never commit .env)
docker compose up -d    # start ClickHouse (HTTP on host port 8124)
```

## Run the daily backfill

```bash
uv run python -m super_trade.ingest.backfill
```

Reads `.env` for ClickHouse, fetches only the missing tail per symbol (the store
is the cache), and writes idempotently.

## Explore in the dashboard

```bash
uv run streamlit run dashboard/app.py
```

Opens at `http://localhost:8501`. Defaults to the `super_trade_sandbox` database
(realistic synthetic data) so charts show immediately.

## A quick backtest

```python
from super_trade.data import ClickHouseStore, ClickHouseConfig, Interval
from super_trade.backtest import VectorizedEngine, SmaCross

with ClickHouseStore(ClickHouseConfig()) as store:
    bars = store.read_bars("600519", Interval.DAY)

result = VectorizedEngine().run(bars, SmaCross(10, 30))
print(result.stats())
result.equity_curve().show()
```

## Development

```bash
uv run ruff format . && uv run ruff check --fix .   # or the /ruff-fix skill
uv run pytest -m "not integration"                  # fast unit tier
uv run pytest                                        # + integration (needs ClickHouse)
```
