---
title: 采集（sources）
---

# 采集 — `super_trade.sources`

行情数据的来源。采集层依赖 `DataSource` 接口；akshare 是首个实现，QMT 提供精确/近期数据。

## `DataSource`（抽象基类）

```python
class DataSource(ABC):
    def list_symbols(self) -> list[SymbolInfo]: ...
    def fetch_bars(self, symbol, interval, start=None, end=None,
                   adjust=Adjust.HFQ) -> list[Bar]: ...
```

`Adjust` 是 `StrEnum`：`NONE` / `QFQ`（前复权）/ `HFQ`（后复权）。默认 **HFQ**——随时间
稳定，适合回测。

## AkshareSource

用 `RateLimiter` + `tenacity` 重试包裹每次网络调用，将 akshare 的中文列名规范化为校验过的
`Bar`，并处理 A 股特性（成交量从“手”换算为股；交易日 → UTC）。畸形行会被跳过。

:::warning 东方财富限流
akshare 抓取的站点按 IP 限流。生产环境保持 `RateLimiter(min_interval)` ≥ 1–2 秒。历史
K 线接口还会屏蔽非大陆 / 数据中心 IP。
:::

## QmtSource

通过 MiniQMT 终端 + `xtquant` 获取券商级数据（无抓取/WAF/IP 问题）。模型为**先下载、再
查询**：`download_history_data` 填充本地缓存，随后 `get_market_data_ex(..., dividend_type=...)`。
`xtquant` 采用惰性导入，因此模块在任何机器都能加载；取数路径需在装有 MiniQMT 的机器上验证。

symbol 在存储所用的 6 位裸代码与 QMT 的 `代码.交易所` 形式之间映射
（`600519` ↔ `600519.SH`）。
