---
title: 存储（data）
---

# 存储 — `super_trade.data`

行情数据存放之处。系统其余部分依赖 `DataStore` 接口，而非 ClickHouse 本身。

## 模型

`Bar`（Pydantic，不可变）——经校验的 OHLCV，包含 `symbol`、`interval`、`timestamp`
（UTC）、`open/high/low/close`、`volume`。校验强制 OHLC 一致性（`high >= low`、开/收价
位于区间内、成交量非负）。`Interval` 是 `StrEnum`（`1m`/`5m`/`15m`/`1h`/`1d`）；
`BAR_COLUMNS` 是规范的列顺序。

## `DataStore`（抽象基类）

```python
class DataStore(ABC):
    def init_schema(self) -> None: ...
    def write_bars(self, bars) -> int: ...                 # list[Bar] 或 Polars DF
    def read_bars(self, symbol, interval, start=None, end=None) -> pl.DataFrame: ...
    def latest_timestamp(self, symbol, interval) -> datetime | None: ...  # 缓存键
    def list_symbols(self, interval=None) -> list[str]: ...
```

## ClickHouse 后端

`ClickHouseStore` 使用官方的 `clickhouse-connect` 驱动：

- **批量、列式写入**——绝不逐行 ORM 写入。
- **`ReplacingMergeTree`**，以 `(symbol, interval, timestamp)` 为键、`ingested_at`
  为版本——重复写入重叠区间时是替换而非重复。读取使用 `FINAL` 在查询期去重。
- **列编解码器**（时间戳用 `DoubleDelta`、价格用 `Gorilla`、成交量用 `T64`）——对金融
  序列有很高的压缩收益。
- **`PARTITION BY toYYYYMM(timestamp)`** 便于时间范围裁剪。

`ClickHouseConfig` 是一个 `pydantic-settings` 模型，从环境变量 / `.env` 读取
`CLICKHOUSE_*`。
