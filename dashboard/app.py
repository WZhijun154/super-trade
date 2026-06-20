"""Streamlit dashboard for exploring super-trade market data.

A thin presentation layer: it reads bars through a ``DataStore``, computes
indicators with ``super_trade.metrics``, and renders them with
``super_trade.viz`` — no business logic of its own.

Run: uv run streamlit run dashboard/app.py
"""

from __future__ import annotations

import streamlit as st

from super_trade import metrics as m
from super_trade.data import ClickHouseConfig, ClickHouseStore, Interval
from super_trade.viz import charts

st.set_page_config(page_title="super-trade", layout="wide")


@st.cache_resource
def get_store(database: str) -> ClickHouseStore:
    return ClickHouseStore(ClickHouseConfig(database=database))


st.title("super-trade — market data explorer")

sb = st.sidebar
database = sb.text_input("ClickHouse database", value="super_trade_sandbox")
store = get_store(database)

try:
    symbols = store.list_symbols()
except Exception as exc:
    st.error(f"Could not reach ClickHouse / database '{database}': {exc}")
    st.stop()

if not symbols:
    st.warning(
        f"No symbols in '{database}'. Seed some with scripts/seed_sandbox.py, "
        "run the backfill, or choose another database."
    )
    st.stop()

symbol = sb.selectbox("Symbol", symbols)

sb.subheader("Indicators")
show_sma = sb.checkbox("SMA", value=True)
sma_window = int(sb.number_input("SMA window", 2, 250, 20))
show_ema = sb.checkbox("EMA", value=False)
ema_span = int(sb.number_input("EMA span", 2, 250, 12))
show_boll = sb.checkbox("Bollinger Bands (20)", value=False)
show_volume = sb.checkbox("Volume", value=True)
show_rsi = sb.checkbox("RSI (14)", value=True)
show_macd = sb.checkbox("MACD", value=False)

df = store.read_bars(symbol, Interval.DAY)
if df.height == 0:
    st.warning(f"No bars stored for {symbol}.")
    st.stop()

# Build the indicator columns the user selected.
overlays: list[str] = []
exprs = []
if show_sma:
    exprs.append(m.sma("close", sma_window).alias(f"sma_{sma_window}"))
    overlays.append(f"sma_{sma_window}")
if show_ema:
    exprs.append(m.ema("close", ema_span).alias(f"ema_{ema_span}"))
    overlays.append(f"ema_{ema_span}")
if exprs:
    df = df.with_columns(exprs)
if show_boll:
    df = df.with_columns(m.bollinger_bands("close", 20).alias("bb")).unnest("bb")
    overlays += ["upper", "middle", "lower"]

subplots: list[list[str]] = []
if show_rsi:
    df = df.with_columns(m.rsi("close", 14).alias("rsi_14"))
    subplots.append(["rsi_14"])
if show_macd:
    df = df.with_columns(m.macd().alias("macd")).unnest("macd")
    subplots.append(["macd", "signal"])

fig = charts.price_with_indicators(
    df, overlays=overlays, volume=show_volume, subplots=subplots, title=symbol
)
fig.update_layout(height=720)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Summary statistics")
stats = df.select(
    m.total_return().alias("total_return"),
    m.cagr().alias("cagr"),
    m.annualized_volatility().alias("ann_vol"),
    m.sharpe_ratio().alias("sharpe"),
    m.max_drawdown().alias("max_drawdown"),
    m.calmar_ratio().alias("calmar"),
)
st.dataframe(stats.to_pandas(), use_container_width=True, hide_index=True)
