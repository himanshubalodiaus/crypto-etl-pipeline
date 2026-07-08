"""Tests for transform.py — the pure-logic data transformations."""

import pandas as pd
import pytest

from transform import to_daily, add_derived_metrics, transform


def _rows(coin, prices, start="2026-06-01"):
    """Helper: build one daily row per price for a coin."""
    dates = pd.date_range(start, periods=len(prices), freq="D", tz="UTC")
    return [
        {"coin_id": coin, "captured_at": d.isoformat(),
         "price_usd": p, "market_cap": p * 1000, "volume_24h": p * 10}
        for d, p in zip(dates, prices)
    ]


def test_to_daily_collapses_multiple_readings_per_day():
    # Two readings on the same day for the same coin should collapse to one,
    # keeping the LAST price of the day.
    rows = [
        {"coin_id": "bitcoin", "captured_at": "2026-06-01T08:00:00+00:00",
         "price_usd": 100, "market_cap": 1, "volume_24h": 1},
        {"coin_id": "bitcoin", "captured_at": "2026-06-01T20:00:00+00:00",
         "price_usd": 150, "market_cap": 1, "volume_24h": 1},
    ]
    daily = to_daily(rows)
    assert len(daily) == 1
    assert daily.iloc[0]["price_usd"] == 150


def test_mixed_timestamp_formats_parse():
    # Some timestamps have fractional seconds, some don't — must not crash.
    rows = [
        {"coin_id": "bitcoin", "captured_at": "2026-06-01T08:00:52+00:00",
         "price_usd": 100, "market_cap": 1, "volume_24h": 1},
        {"coin_id": "bitcoin", "captured_at": "2026-06-02T08:00:52.123456+00:00",
         "price_usd": 110, "market_cap": 1, "volume_24h": 1},
    ]
    daily = to_daily(rows)
    assert len(daily) == 2


def test_daily_return_pct_is_correct():
    # 100 -> 110 is a +10% daily return.
    df = transform(_rows("bitcoin", [100, 110]))
    assert df.iloc[0]["daily_return_pct"] != df.iloc[0]["daily_return_pct"]  # first is NaN
    assert round(df.iloc[1]["daily_return_pct"], 2) == 10.0


def test_moving_average_matches_manual_mean():
    # ma_7d on day 3 (with min_periods=1) should be the mean of the first 3 prices.
    prices = [10, 20, 30]
    df = transform(_rows("bitcoin", prices))
    assert round(df.iloc[2]["ma_7d"], 4) == round(sum(prices) / 3, 4)


def test_coins_do_not_bleed_into_each_other():
    # The first row of each coin should have a NaN return (no prior day for THAT coin),
    # proving the groupby keeps coins separate.
    rows = _rows("bitcoin", [100, 200]) + _rows("ethereum", [5, 6])
    df = transform(rows)
    eth_first = df[df["coin_id"] == "ethereum"].iloc[0]
    assert pd.isna(eth_first["daily_return_pct"])


def test_output_has_expected_columns():
    df = transform(_rows("bitcoin", [100, 110, 120]))
    for col in ["coin_id", "captured_at", "price_usd", "daily_return_pct",
                "ma_7d", "ma_30d", "volatility_7d"]:
        assert col in df.columns