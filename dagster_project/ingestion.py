"""Raw ingestion: load `raw_data/` CSVs into DuckDB's `raw` schema.

Kept as plain functions (not Dagster-decorated) so they're usable both as
Dagster assets (see `assets.py`) and standalone / from tests — the actual
ingestion logic has nothing Dagster-specific about it.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = REPO_ROOT / "raw_data"
WAREHOUSE_PATH = REPO_ROOT / "warehouse.duckdb"


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(WAREHOUSE_PATH))
    con.execute("create schema if not exists raw")
    return con


def load_plans() -> int:
    con = _connect()
    try:
        con.execute(f"""
            create or replace table raw.plans as
            select * from read_csv_auto('{RAW_DATA_DIR / "plans.csv"}')
        """)
        return con.execute("select count(*) from raw.plans").fetchone()[0]
    finally:
        con.close()


def load_crm_customers() -> int:
    """Unions every daily snapshot file into one raw table (one row per
    customer per snapshot day) -- the `int_customer_history` dbt model turns
    this into dim_customer's SCD2 history."""
    con = _connect()
    try:
        glob_path = str(RAW_DATA_DIR / "crm_customers" / "customers_*.csv")
        con.execute(f"""
            create or replace table raw.crm_customers as
            select * from read_csv_auto('{glob_path}')
        """)
        return con.execute("select count(*) from raw.crm_customers").fetchone()[0]
    finally:
        con.close()


def load_invoices() -> int:
    con = _connect()
    try:
        con.execute(f"""
            create or replace table raw.invoices as
            select * from read_csv_auto('{RAW_DATA_DIR / "invoices.csv"}')
        """)
        return con.execute("select count(*) from raw.invoices").fetchone()[0]
    finally:
        con.close()


def load_usage_events() -> int:
    con = _connect()
    try:
        con.execute(f"""
            create or replace table raw.usage_events as
            select * from read_csv_auto('{RAW_DATA_DIR / "usage_events.csv"}')
        """)
        return con.execute("select count(*) from raw.usage_events").fetchone()[0]
    finally:
        con.close()


def load_all() -> dict[str, int]:
    return {
        "plans": load_plans(),
        "crm_customers": load_crm_customers(),
        "invoices": load_invoices(),
        "usage_events": load_usage_events(),
    }


if __name__ == "__main__":
    counts = load_all()
    for name, n in counts.items():
        print(f"raw.{name}: {n} rows loaded")
