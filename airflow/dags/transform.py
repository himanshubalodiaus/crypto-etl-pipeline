"""


Takes the raw history rows from backfill.py and turns them into something
worth looking at: clean daily prices plus derived metrics — daily returns,
7- and 30-day moving averages, and volatility. This is where raw numbers
become insight.

Uses pandas, the standard Python library for working with tabular data.

Run it directly to see it work (it will backfill first, then transform):
    pip install pandas
    python transform.py
"""

from __future__ import annotations

import pandas as pd


# --- Step 1: collapse to one clean row per coin per day ----------------------
def to_daily(rows: list[dict]) -> pd.DataFrame:
    """
    The backfill may return one point per day already — but it might return
    several per day depending on the API. To be safe, we collapse to exactly
    one row per coin per day, keeping that day's *last* value (the daily close).
    """
    df = pd.DataFrame(rows)

    # Turn the text timestamp into a real datetime pandas can do math on.
    # format="ISO8601" handles timestamps that are ISO-formatted but vary
    # slightly (some with fractional seconds, some without).
    df["captured_at"] = pd.to_datetime(df["captured_at"], utc=True, format="ISO8601")

    # normalize() strips the time-of-day, leaving just the date
    df["date"] = df["captured_at"].dt.normalize()

    # For each coin+date, keep the last reading of that day
    daily = (
        df.sort_values("captured_at")
          .groupby(["coin_id", "date"], as_index=False)
          .agg({"price_usd": "last", "market_cap": "last", "volume_24h": "last"})
    )

    daily = daily.rename(columns={"date": "captured_at"})
    return daily.sort_values(["coin_id", "captured_at"]).reset_index(drop=True)


# --- Step 2: compute the derived metrics -------------------------------------
def add_derived_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add the columns that make the data interesting. Everything is computed
    *per coin* (grouped), so Bitcoin's moving average never mixes with Ethereum's.
    """
    df = df.copy()
    by_coin = df.groupby("coin_id")

    # Day-over-day percentage change in price
    df["daily_return_pct"] = by_coin["price_usd"].pct_change() * 100

    # 7-day and 30-day moving averages (the smoothed trend lines)
    df["ma_7d"] = by_coin["price_usd"].transform(
        lambda s: s.rolling(window=7, min_periods=1).mean()
    )
    df["ma_30d"] = by_coin["price_usd"].transform(
        lambda s: s.rolling(window=30, min_periods=1).mean()
    )

    # Volatility = how bumpy the daily returns have been over the last 7 days
    df["volatility_7d"] = df.groupby("coin_id")["daily_return_pct"].transform(
        lambda s: s.rolling(window=7, min_periods=2).std()
    )

    return df


# --- The transform step, start to finish -------------------------------------
def transform(rows: list[dict]) -> pd.DataFrame:
    """Raw history rows in, enriched daily table out."""
    daily = to_daily(rows)
    enriched = add_derived_metrics(daily)
    return enriched


# --- Run directly to see it work ---------------------------------------------
if __name__ == "__main__":
    from backfill import backfill

    print("Backfilling history first...\n")
    rows = backfill()

    print("\nTransforming...\n")
    df = transform(rows)

    # Show the most recent few days for Bitcoin so the metrics are visible
    btc = df[df["coin_id"] == "bitcoin"].tail(7)

    pd.set_option("display.float_format", lambda x: f"{x:,.2f}")
    print("Latest 7 days for bitcoin (with derived metrics):\n")
    print(btc[["captured_at", "price_usd", "daily_return_pct",
               "ma_7d", "ma_30d", "volatility_7d"]].to_string(index=False))

    print(f"\nTotal rows after transform: {len(df)}")
    print(f"Columns: {list(df.columns)}")