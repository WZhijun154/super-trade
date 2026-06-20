---
title: Pipeline (ingest)
---

# Pipeline — `super_trade.ingest`

Orchestration. A plain scheduled run is enough — the pipeline is a linear loop,
not a DAG.

## DailyBackfill

Walks the universe and syncs each symbol's daily bars into a `DataStore`:

- **The store is the cache.** `store.latest_timestamp(symbol)` says how far a
  symbol is loaded, so only the missing tail is fetched (plus a short lookback to
  recapture corrections).
- **Idempotent.** Writes go to a `ReplacingMergeTree`, so interrupted or repeated
  runs are safe.
- **Per-symbol failure isolation** — one symbol failing doesn't abort the run;
  failures are collected in a `BackfillReport`.

```bash
uv run python -m super_trade.ingest.backfill
```

## Reliability lives in the source

`RateLimiter` (per-process request spacing) plus the source's `tenacity` retries
keep the orchestrator simple. Multi-node scaling only helps with **distinct egress
IPs** (eastmoney throttles per IP).

## Observability

Use **Logfire**, not stdlib `logging`, in app code. `configure_logfire()` is called
at process entry; telemetry only ships when `LOGFIRE_TOKEN` is set, so local/CI/
offline runs work without setup.

## Future orchestration

If real scheduling / parallel fan-out / run history is needed: **Prefect/Dagster**
or the in-house **astraq** task queue — not pydantic-graph (a state-machine lib for
agent flows, not ETL).
