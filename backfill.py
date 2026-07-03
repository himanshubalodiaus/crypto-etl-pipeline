from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

# Reuse the pieces we already built in extract.py
from extract import COINS, VS_CURRENCY, _build_session


# --- Configuration -----------------------------------------------------------
HISTORY_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
DAYS = 90                       # how far back to pull
POLITE_DELAY_SECONDS = 2.5      # pause between coins so we don't hit rate limits
CACHE_FILE = Path(".cache_backfill.json")
CACHE_TTL_SECONDS = 3600        # backfill data changes slowly; cache for an hour


# --- Cache helpers (same idea as extract.py) ---------------------------------
def _read_cache() -> list[dict] | None:
    if not CACHE_FILE.exists():
        return None
    age = time.time() - CACHE_FILE.stat().st_mtime
    if age > CACHE_TTL_SECONDS:
        return None
    try:
        return json.loads(CACHE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(data: list[dict]) -> None:
    try:
        CACHE_FILE.write_text(json.dumps(data))
    except OSError:
        pass


# --- Fetch history for a single coin -----------------------------------------
def fetch_history(coin_id: str, days: int, session) -> list[dict]:
    """
    Pull `days` of history for one coin.

    CoinGecko returns three parallel lists — prices, market caps, and volumes —
    each a series of [timestamp_ms, value] pairs. We stitch them back together
    into one clean row per point in time.
    """
    url = HISTORY_URL.format(coin_id=coin_id)
    params = {"vs_currency": VS_CURRENCY, "days": days}

    response = session.get(url, params=params, timeout=20)
    response.raise_for_status()
    raw = response.json()

    prices = raw.get("prices", [])
    market_caps = raw.get("market_caps", [])
    volumes = raw.get("total_volumes", [])

    rows = []
    for i, (ts_ms, price) in enumerate(prices):
        # Convert milliseconds-since-epoch into a readable UTC timestamp
        captured_at = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
        rows.append({
            "coin_id": coin_id,
            "captured_at": captured_at,
            "price_usd": price,
            # market_caps / volumes line up by index; guard in case they don't
            "market_cap": market_caps[i][1] if i < len(market_caps) else None,
            "volume_24h": volumes[i][1] if i < len(volumes) else None,
        })
    return rows


# --- Backfill all coins ------------------------------------------------------
def backfill(coins: list[str] = COINS, days: int = DAYS, use_cache: bool = True) -> list[dict]:
    """Fetch history for every coin and return one combined list of rows."""
    if use_cache:
        cached = _read_cache()
        if cached is not None:
            print("(using cached backfill data)")
            return cached

    session = _build_session()
    all_rows: list[dict] = []

    for n, coin_id in enumerate(coins):
        print(f"Fetching {days}d history for {coin_id} ({n + 1}/{len(coins)})...")
        all_rows.extend(fetch_history(coin_id, days, session))
        # Be polite to the free API: pause between coins, but not after the last
        if n < len(coins) - 1:
            time.sleep(POLITE_DELAY_SECONDS)

    if use_cache:
        _write_cache(all_rows)

    return all_rows


# --- Run directly to see it work ---------------------------------------------
if __name__ == "__main__":
    rows = backfill()

    print(f"\nDone. Pulled {len(rows)} total data points across {len(COINS)} coins.\n")

    # Summarize per coin: how many points, the date range, first vs last price
    print(f"{'COIN':<14}{'POINTS':>8}{'FIRST':>12}{'LATEST':>12}")
    print("-" * 46)
    for coin_id in COINS:
        coin_rows = [r for r in rows if r["coin_id"] == coin_id]
        if not coin_rows:
            continue
        first_price = coin_rows[0]["price_usd"]
        last_price = coin_rows[-1]["price_usd"]
        print(f"{coin_id:<14}{len(coin_rows):>8}{first_price:>12,.2f}{last_price:>12,.2f}")

    print(f"\nDate range: {rows[0]['captured_at'][:10]} → {rows[-1]['captured_at'][:10]}")