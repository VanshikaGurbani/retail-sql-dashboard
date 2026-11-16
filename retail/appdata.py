"""Data access for the Streamlit app. It reads only the CSV files in exports/ (so the app can
be deployed without the 46 MB download) and runs the queries in sql/app/*.sql against them in
an in-memory DuckDB. No Streamlit import here, so tests can call it directly."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import duckdb
import pandas as pd

from retail import config as C

APP_SQL = C.SQL_DIR / "app"
VIEWS = {
    "orders": "mart_orders.csv",
    "cohorts": "mart_cohorts.csv",
    "rfm": "mart_rfm.csv",
    "rfm_summary": "mart_rfm_summary.csv",
    "product_months_app": "mart_product_months_app.csv",
    "scenario_assumptions": "mart_scenario_assumptions.csv",
    "monthly": "mart_monthly.csv",
}


def export_dir() -> Path:
    return Path(os.environ.get("RETAIL_EXPORT_DIR", C.EXPORT_DIR))


def connect(directory: Path | None = None) -> duckdb.DuckDBPyConnection:
    directory = directory or export_dir()
    con = duckdb.connect(":memory:")
    for view, fname in VIEWS.items():
        path = (directory / fname).resolve().as_posix().replace("'", "''")
        con.execute(f"CREATE VIEW {view} AS SELECT * FROM read_csv('{path}', header=true)")
    return con


def query(con: duckdb.DuckDBPyConnection, name: str, **params) -> pd.DataFrame:
    sql = (APP_SQL / f"{name}.sql").read_text(encoding="utf-8")
    wanted = {k: v for k, v in params.items() if f"${k}" in sql}
    return con.execute(sql, wanted).df()


def bounds(con: duckdb.DuckDBPyConnection) -> tuple[dt.date, dt.date, list[str]]:
    lo, hi = con.execute("SELECT min(invoice_date), max(invoice_date) FROM orders").fetchone()
    countries = [
        r[0]
        for r in con.execute(
            "SELECT country FROM orders GROUP BY country ORDER BY sum(order_value) DESC"
        ).fetchall()
    ]
    return lo, hi, countries
