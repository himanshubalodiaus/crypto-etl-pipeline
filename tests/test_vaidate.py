"""Tests for validate.py — the data-quality gate."""

import pandas as pd
import pytest

from validate import validate, ValidationError


def _good_df(n_coins=10):
    """A clean DataFrame that should pass every check."""
    return pd.DataFrame([
        {"coin_id": f"coin{i}",
         "captured_at": pd.Timestamp("2026-06-30", tz="UTC"),
         "price_usd": 100.0 + i}
        for i in range(n_coins)
    ])


def test_good_data_passes():
    report = validate(_good_df(), raise_on_fail=False)
    assert report["passed"] is True
    assert report["hard_problems"] == []


def test_missing_price_is_caught():
    df = _good_df()
    df.loc[0, "price_usd"] = None
    report = validate(df, raise_on_fail=False)
    assert report["passed"] is False
    assert any("missing" in p for p in report["hard_problems"])


def test_negative_price_is_caught():
    df = _good_df()
    df.loc[0, "price_usd"] = -5.0
    report = validate(df, raise_on_fail=False)
    assert report["passed"] is False
    assert any("<= 0" in p for p in report["hard_problems"])


def test_duplicate_day_is_caught():
    df = _good_df(1)
    df = pd.concat([df, df], ignore_index=True)  # duplicate the single row
    report = validate(df, raise_on_fail=False)
    assert any("duplicate" in p for p in report["hard_problems"])


def test_future_timestamp_is_caught():
    df = _good_df(1)
    df.loc[0, "captured_at"] = pd.Timestamp("2099-01-01", tz="UTC")
    report = validate(df, raise_on_fail=False)
    assert any("future" in p for p in report["hard_problems"])


def test_too_few_coins_is_a_warning_not_a_failure():
    # 5 coins < 10 expected: should WARN but still pass (it's a soft check).
    report = validate(_good_df(5), raise_on_fail=False)
    assert report["passed"] is True          # not a hard failure
    assert len(report["warnings"]) >= 1       # but flagged


def test_raise_on_fail_raises_on_bad_data():
    df = _good_df()
    df.loc[0, "price_usd"] = None
    with pytest.raises(ValidationError):
        validate(df, raise_on_fail=True)