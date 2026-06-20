---
title: 流水线（ingest）
---

# 流水线 — `super_trade.ingest`

编排层。一次普通的定时运行即可——流水线是线性循环，而非 DAG。

## DailyBackfill

遍历股票池，将每只股票的日线同步进 `DataStore`：

- **存储即缓存。** `store.latest_timestamp(symbol)` 告知某 symbol 已加载到何处，因此只
  抓取缺失的尾部（外加一小段回看窗口以重新捕获修正）。
- **幂等。** 写入进入 `ReplacingMergeTree`，因此中断或重复运行都是安全的。
- **按 symbol 隔离失败**——单只失败不会中止整轮；失败汇总进 `BackfillReport`。

```bash
uv run python -m super_trade.ingest.backfill
```

## 可靠性内建于数据源

`RateLimiter`（按进程的请求间隔）加上数据源自带的 `tenacity` 重试，让编排器保持简单。
多节点扩展只有在**不同出口 IP** 时才有用（东方财富按 IP 限流）。

## 可观测性

应用代码使用 **Logfire**，而非标准库 `logging`。`configure_logfire()` 在进程入口被调用；
只有设置了 `LOGFIRE_TOKEN` 才会上报数据，因此本地/CI/离线运行无需任何配置。

## 未来的编排

若需要真正的调度 / 并行扇出 / 运行历史：使用 **Prefect/Dagster** 或自研的 **astraq**
任务队列——而非 pydantic-graph（它是用于智能体流程的状态机库，不是 ETL 工具）。
