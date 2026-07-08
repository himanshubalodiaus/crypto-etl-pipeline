"""

Runs a set of sanity checks on the transformed data *before* it's allowed
into the database. The goal: catch obviously-broken data early and loudly,
rather than silently storing garbage that corrupts your dashboard later.

Each check returns a list of problems. If any check finds problems, the data
is considered invalid. We separate "hard" failures (data we must never store)
from "soft" warnings (things worth flagging but not fatal).

Run it directly to see it work (backfills, transforms, then validates):
    python validate.py
"""

from __future__ import annotations

import pandas as pd


# Plausible bounds. Anything outside these is almost certainly bad data.
MAX_PLAUSIBLE_PRICE = 10_000_000     # no single coin is worth $10M
EXPECTED_COINS = 10                  # how many distinct coins we expect


class ValidationError(Exception):
    """Raised when the data fails a hard check and must not be stored."""


# --- Individual checks -------------------------------------------------------
def check_no_missing_prices(df: pd.DataFrame) -> list[str]:
    """Price is the one field we can't do without. It must never be null."""
    missing = df["price_usd"].isna().sum()
    if missing:
        return [f"{missing} rows have a missing price_usd"]
    return []


def check_prices_positive(df: pd.DataFrame) -> list[str]:
    """Prices must be greater than zero and within a plausible range."""
    problems = []
    non_positive = (df["price_usd"] <= 0).sum()
    if non_positive:
        problems.append(f"{non_positive} rows have a price <= 0")
    too_big = (df["price_usd"] > MAX_PLAUSIBLE_PRICE).sum()
    if too_big:
        problems.append(f"{too_big} rows have an implausibly large price")
    return problems


def check_no_duplicate_days(df: pd.DataFrame) -> list[str]:
    """We expect exactly one row per coin per day."""
    dupes = df.duplicated(subset=["coin_id", "captured_at"]).sum()
    if dupes:
        return [f"{dupes} duplicate coin+day rows found"]
    return []


def check_timestamps_not_future(df: pd.DataFrame) -> list[str]:
    """No data point should be timestamped in the future."""
    now = pd.Timestamp.now(tz="UTC")
    future = (df["captured_at"] > now).sum()
    if future:
        return [f"{future} rows have a timestamp in the future"]
    return []


def check_expected_coins_present(df: pd.DataFrame) -> list[str]:
    """Flag if we got fewer coins than expected (e.g. an API call silently failed)."""
    n_coins = df["coin_id"].nunique()
    if n_coins < EXPECTED_COINS:
        return [f"only {n_coins} coins present, expected {EXPECTED_COINS}"]
    return []


# --- Orchestrating the checks ------------------------------------------------
# Hard checks: failing any of these means we refuse to store the data.
HARD_CHECKS = [
    check_no_missing_prices,
    check_prices_positive,
    check_no_duplicate_days,
    check_timestamps_not_future,
]

# Soft checks: worth warning about, but not fatal.
SOFT_CHECKS = [
    check_expected_coins_present,
]


def validate(df: pd.DataFrame, raise_on_fail: bool = True) -> dict:
    """
    Run all checks. Returns a report dict. If raise_on_fail is True and any
    hard check fails, raises ValidationError so the pipeline stops before load.
    """
    hard_problems: list[str] = []
    for check in HARD_CHECKS:
        hard_problems.extend(check(df))

    soft_problems: list[str] = []
    for check in SOFT_CHECKS:
        soft_problems.extend(check(df))

    report = {
        "passed": len(hard_problems) == 0,
        "rows_checked": len(df),
        "hard_problems": hard_problems,
        "warnings": soft_problems,
    }

    if raise_on_fail and hard_problems:
        raise ValidationError(
            "Data failed validation and will not be stored:\n  - "
            + "\n  - ".join(hard_problems)
        )

    return report


# --- Run directly to see it work ---------------------------------------------
if __name__ == "__main__":
    from backfill import backfill
    from transform import transform

    print("Backfilling and transforming first...\n")
    df = transform(backfill())

    print("Validating...\n")
    report = validate(df, raise_on_fail=False)

    print(f"Rows checked : {report['rows_checked']}")
    print(f"Passed       : {report['passed']}")

    if report["hard_problems"]:
        print("\nHARD PROBLEMS (would block storage):")
        for p in report["hard_problems"]:
            print(f"  - {p}")
    else:
        print("\nNo hard problems — data is safe to store.")

    if report["warnings"]:
        print("\nWarnings (non-fatal):")
        for w in report["warnings"]:
            print(f"  - {w}")