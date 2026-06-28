---
title: 存储（data）
---

# 存储 — `super_trade.data`

行情数据存放之处。系统其余部分依赖 `DataStore` 接口，而非 ClickHouse 本身。

## 模型

`Bar`（Pydantic，不可变）——经校验的 OHLCV，包含 `symbol`、`interval`、`timestamp`
（UTC）、`open/high/low/close`、`volume`。校验强制 OHLC 一致性（`high >= low`、开/收价
位于区间内、成交量非负）。`Interval` 是 `StrEnum`（`1m`/`5m`/`15m`/`30m`/`1h`/`1d`），
带有 `.minutes` 与 `.is_intraday` 辅助属性；`BAR_COLUMNS` 是规范的列顺序。

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

## 周期与重采样（resampling）

**以 1 分钟 K 线作为唯一数据源存储；更粗的周期在读取时由重采样派生。** 唯一数据源意味着
无冗余、且保证一致性——一根 5 分钟 K 线*永远*恰好等于它对应的五根 1 分钟 K 线，而不是另行
抓取、可能漂移的独立序列。

```python
from super_trade.data import Interval, load_bars

# 以 1m 存储；读取时重采样为 5m。
df = load_bars(store, "600519", Interval.FIVE_MINUTE, resample_from=Interval.MINUTE)

# 日线直接读取（无需重采样）。
df = load_bars(store, "600519", Interval.DAY)
```

`load_bars(store, symbol, interval, start, end, *, resample_from=None)` 在
`resample_from` 为 `None` 时直接读取，否则读取更细的序列再调用 `resample(...)`。重采样
本身是纯 Polars 实现（`data/resample.py`）：`resample(bars, target, *, source=Interval.MINUTE)`。

### 按交易时段分桶（A 股的关键坑）

A 股交易时段为**北京时间 09:30–11:30 与 13:00–15:00**，中间有午休。朴素的墙钟时间窗口会
出错：60 分钟 K 线无法落在整点网格上（09:30 不在整点），且上午、下午两个时段无法共用同一
偏移量。因此重采样器在**每个 `(symbol, date, session)`（标的、日期、时段）内部**分桶：

```
bucket = (距时段开盘的分钟数) // target.minutes
```

它对每个周期都正确，且**绝不跨越午休或隔夜跳空**。OHLCV 聚合方式为：`open=首根`、
`high=最大`、`low=最小`、`close=末根`、`volume=求和`（首/末按 timestamp 排序）。日内 K 线
以桶内第一根 1 分钟 K 线的时刻（UTC）作为标签；日线以北京日期的 UTC 零点作为标签（与
akshare 日线约定一致）。向**更细**的周期重采样会抛出 `ValueError`。

真实的 1 分钟历史来自 **QMT**（`QmtSource`）；akshare 仍只提供日线。下游的一切——指标、两个
回测层、执行——本就接收一个 K 线 DataFrame，因此可原样消费重采样后的数据。示例与仪表盘都
接受一个周期参数，并在为日内周期时从 1 分钟重采样。
