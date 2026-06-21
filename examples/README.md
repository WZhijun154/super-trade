# Examples

Runnable scripts demonstrating the platform. They read **real bars** from a
`DataStore`, defaulting to the `super_trade_sandbox` database (seed it with
`uv run python scripts/seed_sandbox.py`). Pass a symbol/database to use your own:

```bash
uv run python examples/vectorized_backtest.py            # FAKE003, sandbox
uv run python examples/vectorized_backtest.py 600519 super_trade

uv run python examples/event_driven_backtest.py
```

| Script | Engine | Shows |
|---|---|---|
| `vectorized_backtest.py` | `VectorizedEngine` (fast, signal research) | runs 3 strategies, prints stats, saves an equity-curve HTML |
| `event_driven_backtest.py` | `EventDrivenBacktest` (bar-by-bar, real cash/lots) | compares with vs without a stop-loss, saves equity HTML + trade log |

Prereqs: ClickHouse running (`docker compose up -d`) and data present. See the
[docs](https://wzhijun154.github.io/super-trade/) for the concepts behind each engine.
