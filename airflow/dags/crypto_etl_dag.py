"""
crypto_etl_dag.py — the Airflow DAG for the crypto ETL pipeline.

Turns the pipeline into four scheduled, monitored tasks that run in order:
    backfill  ->  transform  ->  validate  ->  load

Airflow's scheduler runs this daily. Each task shows up as its own box in the
Airflow UI's graph view, with its own status, logs, and retry behaviour.

This file imports the pipeline functions you already wrote — it doesn't
reimplement anything. The clean function boundaries you built pay off here.
"""

from __future__ import annotations

import os
import pendulum

from airflow.sdk import dag, task


# The four pipeline modules (backfill.py, transform.py, etc.) sit alongside
# this file in the dags/ folder, so they import directly.
from backfill import backfill
from transform import transform
from validate import validate
from load import get_engine, create_table, load


@dag(
    dag_id="crypto_etl_pipeline",
    schedule="@daily",                       # run once a day
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,                           # don't back-run missed days
    tags=["crypto", "etl", "portfolio"],
    doc_md=__doc__,                          # shows this docstring in the UI
)
def crypto_etl_pipeline():

    @task
    def extract_history() -> list[dict]:
        """Pull historical market data from CoinGecko."""
        rows = backfill(use_cache=False)     # always fetch fresh in scheduled runs
        print(f"Fetched {len(rows)} raw data points")
        return rows

    @task
    def transform_data(rows: list[dict]) -> list[dict]:
        """Clean the data and derive metrics (returns, moving averages, volatility)."""
        import pandas as pd
        df = transform(rows)
        print(f"Transformed into {len(df)} daily rows")
        # Airflow passes data between tasks as JSON, which can't hold pandas
        # Timestamps or NaN. Convert timestamps to ISO strings and NaN to None
        # so the handoff to the next task is clean JSON.
        df["captured_at"] = df["captured_at"].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
        df = df.astype(object).where(pd.notna(df), None)
        return df.to_dict("records")

    @task
    def validate_data(records: list[dict]) -> list[dict]:
        """Quality gate — stops the pipeline here if the data is bad."""
        import pandas as pd
        df = pd.DataFrame(records)
        df["captured_at"] = pd.to_datetime(df["captured_at"], utc=True, format="ISO8601")
        report = validate(df, raise_on_fail=True)   # raises -> task fails -> load never runs
        print(f"Validation passed: {report['rows_checked']} rows")
        return records

    @task
    def load_data(records: list[dict]) -> None:
        """Upsert the validated data into Postgres."""
        import pandas as pd
        df = pd.DataFrame(records)
        df["captured_at"] = pd.to_datetime(df["captured_at"], utc=True, format="ISO8601")
        engine = get_engine()
        create_table(engine)
        n = load(df, engine)
        print(f"Loaded {n} rows into Postgres")

    # Wire the tasks in order. Each task's output feeds the next.
    raw = extract_history()
    transformed = transform_data(raw)
    validated = validate_data(transformed)
    load_data(validated)


crypto_etl_pipeline()