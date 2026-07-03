"""

A Streamlit web app that reads the coin_prices table your pipeline populated
and turns it into charts: price history with moving averages, volatility, and
a table of the day's movers.

Reuses get_engine() from load.py, so it connects the same way (via DATABASE_URL).

Run it:
    pip install streamlit plotly
    streamlit run dashboard.py
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from load import get_engine


st.set_page_config(page_title="Crypto ETL Dashboard", layout="wide")


# --- Data loading ------------------------------------------------------------
@st.cache_data(ttl=300)   # cache for 5 min so we don't re-query on every click
def load_prices() -> pd.DataFrame:
    """Read the whole coin_prices table into a DataFrame."""
    engine = get_engine()
    df = pd.read_sql(
        "SELECT * FROM coin_prices ORDER BY coin_id, captured_at",
        engine,
        parse_dates=["captured_at"],
    )
    # Numeric columns come back from the DB as strings/decimals; make them floats
    numeric_cols = [
        "price_usd", "market_cap", "volume_24h",
        "daily_return_pct", "ma_7d", "ma_30d", "volatility_7d",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# --- Load the data -----------------------------------------------------------
df = load_prices()

st.title("Crypto Market ETL Dashboard")
st.caption("Data pulled, transformed, validated, and stored by my ETL pipeline.")

if df.empty:
    st.warning("No data in the database yet. Run `python load.py` first.")
    st.stop()

# --- Sidebar: pick a coin ----------------------------------------------------
coins = sorted(df["coin_id"].unique())
coin = st.sidebar.selectbox("Choose a coin", coins,
                            index=coins.index("bitcoin") if "bitcoin" in coins else 0)

coin_df = df[df["coin_id"] == coin].sort_values("captured_at")
latest = coin_df.iloc[-1]

# --- Top row: key metrics ----------------------------------------------------
c1, c2, c3 = st.columns(3)
c1.metric(
    "Latest price",
    f"${latest['price_usd']:,.2f}",
    f"{latest['daily_return_pct']:+.2f}%" if pd.notna(latest["daily_return_pct"]) else None,
)
c2.metric("7-day avg", f"${latest['ma_7d']:,.2f}")
c3.metric(
    "Volatility (7d)",
    f"{latest['volatility_7d']:.2f}" if pd.notna(latest["volatility_7d"]) else "n/a",
)

# --- Price chart with moving averages ----------------------------------------
st.subheader(f"{coin.title()} — price & moving averages")
fig = go.Figure()
fig.add_trace(go.Scatter(x=coin_df["captured_at"], y=coin_df["price_usd"],
                         name="Price", line=dict(width=2)))
fig.add_trace(go.Scatter(x=coin_df["captured_at"], y=coin_df["ma_7d"],
                         name="7-day MA", line=dict(width=1, dash="dot")))
fig.add_trace(go.Scatter(x=coin_df["captured_at"], y=coin_df["ma_30d"],
                         name="30-day MA", line=dict(width=1, dash="dash")))
fig.update_layout(height=420, margin=dict(t=10, b=10), hovermode="x unified",
                  yaxis_title="USD", legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)

# --- Volatility chart --------------------------------------------------------
st.subheader("7-day rolling volatility")
vol_fig = go.Figure()
vol_fig.add_trace(go.Scatter(x=coin_df["captured_at"], y=coin_df["volatility_7d"],
                             name="Volatility", fill="tozeroy", line=dict(width=1)))
vol_fig.update_layout(height=260, margin=dict(t=10, b=10), hovermode="x unified")
st.plotly_chart(vol_fig, use_container_width=True)

# --- Movers table: latest daily return for every coin ------------------------
st.subheader("Today's movers (all coins)")
latest_per_coin = (
    df.sort_values("captured_at")
      .groupby("coin_id")
      .tail(1)
      .sort_values("daily_return_pct", ascending=False)
)
movers = latest_per_coin[["coin_id", "price_usd", "daily_return_pct", "volatility_7d"]].copy()
movers.columns = ["Coin", "Price (USD)", "24h Change %", "Volatility (7d)"]
st.dataframe(movers, use_container_width=True, hide_index=True)