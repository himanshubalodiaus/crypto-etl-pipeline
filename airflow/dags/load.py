"""
Writes the validated, enriched data into PostgreSQL. The key idea here is the
*idempotent upsert*: running the pipeline twice never creates duplicate rows.
If a (coin, day) row already exists, it's updated; if not, it's inserted.

Reads the database connection string from the DATABASE_URL environment variable
(never hard-coded — it's a secret, like an API key).

Run it directly to load the full pipeline output:
    pip install sqlalchemy psycopg2-binary
    set DATABASE_URL=postgresql://user:pass@host/dbname   (Windows PowerShell: $env:DATABASE_URL="...")
    python load.py
"""

from __future__ import annotations

import math
import os

import pandas as pd
from sqlalchemy import (
    create_engine, MetaData, Table, Column,
    String, Numeric, DateTime, PrimaryKeyConstraint,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine


# Optionally load a .env file if python-dotenv is installed (handy on Windows
# so you don't have to re-set the env var every terminal session).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# --- Table definition --------------------------------------------------------
# We describe the table to SQLAlchemy once, in Python, and it creates it for us.
metadata = MetaData()

coin_prices = Table(
    "coin_prices", metadata,
    Column("coin_id", String, nullable=False),
    Column("captured_at", DateTime(timezone=True), nullable=False),
    Column("price_usd", Numeric(20, 8), nullable=False),
    Column("market_cap", Numeric(24, 2)),
    Column("volume_24h", Numeric(24, 2)),
    Column("daily_return_pct", Numeric(12, 4)),
    Column("ma_7d", Numeric(20, 8)),
    Column("ma_30d", Numeric(20, 8)),
    Column("volatility_7d", Numeric(12, 4)),
    # This composite key is what makes upserts possible: no two rows can share
    # the same coin + timestamp.
    PrimaryKeyConstraint("coin_id", "captured_at"),
)

# Columns that get overwritten on conflict (everything except the key columns).
UPDATE_COLUMNS = [
    "price_usd", "market_cap", "volume_24h",
    "daily_return_pct", "ma_7d", "ma_30d", "volatility_7d",
]


# --- Connection --------------------------------------------------------------
def get_engine() -> Engine:
    """Build a SQLAlchemy engine from the DATABASE_URL environment variable."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Point it at your Postgres connection string, e.g.\n"
            '  PowerShell:  $env:DATABASE_URL="postgresql://user:pass@host/dbname"'
        )
    # SQLAlchemy wants the psycopg2 driver named explicitly
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url)


def create_table(engine: Engine) -> None:
    """Create the coin_prices table if it doesn't already exist."""
    metadata.create_all(engine)


# --- The load step -----------------------------------------------------------
def _clean_records(df: pd.DataFrame) -> list[dict]:
    """
    Turn the DataFrame into a list of dicts, converting pandas NaN into None.
    Postgres rejects NaN in numeric columns, so this conversion matters.
    """
    records = df.to_dict("records")
    for row in records:
        for key, value in row.items():
            if isinstance(value, float) and math.isnan(value):
                row[key] = None
    return records


def load(df: pd.DataFrame, engine: Engine) -> int:
    """
    Upsert every row into coin_prices. Returns the number of rows processed.

    On conflict (same coin_id + captured_at), the existing row is updated
    rather than a duplicate being inserted — this is what makes re-runs safe.
    """
    records = _clean_records(df)
    if not records:
        return 0

    stmt = pg_insert(coin_prices).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=["coin_id", "captured_at"],
        set_={col: stmt.excluded[col] for col in UPDATE_COLUMNS},
    )

    with engine.begin() as conn:   # begin() = a transaction that auto-commits
        conn.execute(stmt)

    return len(records)


# --- Run directly to see it work ---------------------------------------------
if __name__ == "__main__":
    from backfill import backfill
    from transform import transform
    from validate import validate

    print("Running full pipeline: backfill -> transform -> validate -> load\n")

    df = transform(backfill())
    report = validate(df, raise_on_fail=True)   # stops here if data is bad
    print(f"Validation passed: {report['rows_checked']} rows\n")

    engine = get_engine()
    create_table(engine)
    n = load(df, engine)

    print(f"Loaded {n} rows into Postgres.")
    print("Run it again — the row count in the database won't grow (upsert, not duplicate).")