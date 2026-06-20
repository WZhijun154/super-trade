"""Backtest page — run a strategy and view its equity, drawdown, and stats.

Thin presentation over the backtest/execution engines: pick a symbol + strategy,
choose the vectorized engine (fast) or the event-driven one (path-dependent
stop-loss, real cash/lots), and render the result via ``viz``.
"""

from __future__ import annotations

import streamlit as st

from super_trade.backtest import (
    BuyAndHold,
    CostModel,
    RsiReversion,
    SmaCross,
    VectorizedEngine,
)
from super_trade.data import ClickHouseConfig, ClickHouseStore, Interval
from super_trade.execution import EventDrivenBacktest, RiskLimits, RiskManager

st.set_page_config(page_title="super-trade · backtest", layout="wide")


@st.cache_resource
def get_store(database: str) -> ClickHouseStore:
    return ClickHouseStore(ClickHouseConfig(database=database))


st.title("Backtest")

sb = st.sidebar
database = sb.text_input("ClickHouse database", value="super_trade_sandbox")
store = get_store(database)

try:
    symbols = store.list_symbols()
except Exception as exc:
    st.error(f"Could not reach ClickHouse / database '{database}': {exc}")
    st.stop()
if not symbols:
    st.warning(f"No symbols in '{database}'.")
    st.stop()

symbol = sb.selectbox("Symbol", symbols)

# --- strategy ---
sb.subheader("Strategy")
strat_name = sb.selectbox("Type", ["SMA cross", "RSI reversion", "Buy & hold"])
if strat_name == "SMA cross":
    fast = int(sb.number_input("fast window", 2, 120, 10))
    slow = int(sb.number_input("slow window", 5, 250, 30))
    strategy = SmaCross(fast, slow)
elif strat_name == "RSI reversion":
    window = int(sb.number_input("RSI window", 2, 60, 14))
    low = float(sb.number_input("buy below", 1, 50, 30))
    high = float(sb.number_input("exit above", 50, 99, 70))
    strategy = RsiReversion(window, low, high)
else:
    strategy = BuyAndHold()

# --- engine ---
sb.subheader("Engine")
engine_kind = sb.radio(
    "Type", ["Vectorized (fast)", "Event-driven (stop-loss, real lots)"]
)

df = store.read_bars(symbol, Interval.DAY)
if df.height == 0:
    st.warning(f"No bars stored for {symbol}.")
    st.stop()

if engine_kind.startswith("Vectorized"):
    result = VectorizedEngine(CostModel()).run(df, strategy)
else:
    stop = sb.slider("stop-loss %", 1, 30, 8) / 100
    cash = float(sb.number_input("initial cash", 10_000, 100_000_000, 1_000_000))
    result = EventDrivenBacktest(
        store,
        strategy,
        cash=cash,
        universe=[symbol],
        risk=RiskManager(RiskLimits(stop_loss=stop)),
    ).run()

# --- results ---
stats = result.stats()
st.subheader(f"{symbol} — {result.strategy_name}")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total return", f"{stats['total_return']:.1%}")
c2.metric("CAGR", f"{stats['cagr']:.1%}")
c3.metric("Sharpe", f"{stats['sharpe']:.2f}")
c4.metric("Max drawdown", f"{stats['max_drawdown']:.1%}")
c5.metric("Calmar", f"{stats['calmar']:.2f}")

st.plotly_chart(result.equity_curve(), use_container_width=True)
st.plotly_chart(result.drawdown(), use_container_width=True)
