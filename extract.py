from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# --- Configuration -----------------------------------------------------------
# The coins we track. These are CoinGecko "ids" (not ticker symbols).
COINS = [
    "bitcoin",
    "ethereum",
    "solana",
    "cardano",
    "ripple",
    "dogecoin",
    "polkadot",
    "chainlink",
    "litecoin",
    "avalanche-2",
]

API_URL = "https://api.coingecko.com/api/v3/coins/markets"
VS_CURRENCY = "usd"

# Simple on-disk cache so re-runs during development don't hammer the API.
# CoinGecko's free tier is rate-limited, so being polite matters.
CACHE_FILE = Path(".cache_snapshot.json")
CACHE_TTL_SECONDS = 60  # treat cached data as fresh for 60s


# --- HTTP session with retry/backoff -----------------------------------------
def _build_session() -> requests.Session:
    """A session that automatically retries on transient errors with backoff."""
    session = requests.Session()
    retry = Retry(
        total=4,                       # up to 4 retries
        backoff_factor=1.5,            # wait 1.5s, 3s, 4.5s... between tries
        status_forcelist=[429, 500, 502, 503, 504],  # retry these statuses
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update({"Accept": "application/json"})
    return session


# --- Cache helpers -----------------------------------------------------------
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
        pass  # cache is a nice-to-have, never fatal


# --- The extract step --------------------------------------------------------
def fetch_snapshot(coins: list[str] = COINS, use_cache: bool = True) -> list[dict]:
    """
    Fetch a current market snapshot for the given coins.

    Returns a list of normalized dicts — one per coin — with just the fields
    we care about. Raw API noise is dropped here so downstream steps stay clean.
    """
    if use_cache:
        cached = _read_cache()
        if cached is not None:
            print("(using cached data)")
            return cached

    params = {
        "vs_currency": VS_CURRENCY,
        "ids": ",".join(coins),
        "order": "market_cap_desc",
        "per_page": len(coins),
        "page": 1,
        "price_change_percentage": "24h",
    }

    session = _build_session()
    response = session.get(API_URL, params=params, timeout=15)
    response.raise_for_status()  # raises on 4xx/5xx after retries are exhausted
    raw = response.json()

    captured_at = datetime.now(timezone.utc).isoformat()
    snapshot = [_normalize(row, captured_at) for row in raw]

    if use_cache:
        _write_cache(snapshot)

    return snapshot


def _normalize(row: dict, captured_at: str) -> dict:
    """Pull only the fields we want out of CoinGecko's larger response."""
    return {
        "coin_id": row.get("id"),
        "symbol": (row.get("symbol") or "").upper(),
        "captured_at": captured_at,
        "price_usd": row.get("current_price"),
        "market_cap": row.get("market_cap"),
        "volume_24h": row.get("total_volume"),
        "pct_change_24h": row.get("price_change_percentage_24h"),
    }


# --- Run directly to see it work ---------------------------------------------
if __name__ == "__main__":
    snapshot = fetch_snapshot()

    print(f"\nFetched {len(snapshot)} coins at {snapshot[0]['captured_at']}\n")
    print(f"{'SYMBOL':<8}{'PRICE (USD)':>16}{'24H %':>10}")
    print("-" * 34)
    for coin in snapshot:
        price = coin["price_usd"]
        change = coin["pct_change_24h"]
        change_str = f"{change:+.2f}%" if change is not None else "n/a"
        print(f"{coin['symbol']:<8}{price:>16,.2f}{change_str:>10}")