---
sidebar_position: 2
title: 快速开始
---

# 快速开始

## 前置条件

- Python **3.12** 与 [`uv`](https://docs.astral.sh/uv/)
- Docker（用于 ClickHouse）

## 环境搭建

```bash
uv sync                 # 根据 uv.lock 创建虚拟环境
cp .env.example .env    # 然后填入 CLICKHOUSE_*（切勿提交 .env）
docker compose up -d    # 启动 ClickHouse（HTTP 映射到主机 8124 端口）
```

## 运行日线回填

```bash
uv run python -m super_trade.ingest.backfill
```

读取 `.env` 中的 ClickHouse 配置，按 symbol 只抓取缺失的尾部数据（存储即缓存），并以
幂等方式写入。

## 在仪表盘中探索

```bash
uv run streamlit run dashboard/app.py
```

在 `http://localhost:8501` 打开。默认读取 `super_trade_sandbox` 数据库（真实感的合成
数据），因此图表会立即显示。

## 一个简单回测

```python
from super_trade.data import ClickHouseStore, ClickHouseConfig, Interval
from super_trade.backtest import VectorizedEngine, SmaCross

with ClickHouseStore(ClickHouseConfig()) as store:
    bars = store.read_bars("600519", Interval.DAY)

result = VectorizedEngine().run(bars, SmaCross(10, 30))
print(result.stats())
result.equity_curve().show()
```

## 开发

```bash
uv run ruff format . && uv run ruff check --fix .   # 或使用 /ruff-fix 技能
uv run pytest -m "not integration"                  # 快速单元层
uv run pytest                                        # + 集成层（需要 ClickHouse）
```
