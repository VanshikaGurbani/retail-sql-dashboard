"""Run the SQL files in order and export the marts. All logic lives in sql/*.sql."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pandas as pd

from retail import config as C

NUMBERED_SQL = re.compile(r"^\d{2}_.*\.sql$")


def sql_files(sql_dir: Path = C.SQL_DIR) -> list[Path]:
    return sorted(p for p in sql_dir.iterdir() if NUMBERED_SQL.match(p.name))


def connect(db_path: Path, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=read_only)


def build(raw_csv: Path, db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Build every layer from the flattened raw CSV. `db_path=None` builds in memory."""
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("", ".wal"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)
    con = duckdb.connect(str(db_path) if db_path is not None else ":memory:")
    csv_path = Path(raw_csv).resolve().as_posix().replace("'", "''")
    for path in sql_files():
        con.execute(path.read_text(encoding="utf-8").replace("{{RAW_CSV}}", csv_path))
    return con


RATE_WORDS = ("rate", "share", "growth", "index", "ratio")


def _tidy(df: pd.DataFrame) -> pd.DataFrame:
    """Decimals to floats, rounded: 4 places for ratios, 2 for money and counts."""
    df = df.copy()
    for col in df.columns:
        if (
            str(df[col].dtype) == "object"
            and len(df)
            and df[col].map(lambda v: v.__class__.__name__ == "Decimal").any()
        ):
            df[col] = df[col].astype("float64")
        if pd.api.types.is_float_dtype(df[col]):
            digits = 4 if any(w in col for w in RATE_WORDS) else 2
            df[col] = df[col].round(digits)
    return df


def export_marts(con: duckdb.DuckDBPyConnection, out_dir: Path) -> dict[str, int]:
    """Write each exported mart to mart_<name>.csv (UTF-8, header row) and dq_rule_log.csv."""
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    jobs = [(f"mart.{t}", f"mart_{t}.csv") for t in C.EXPORT_TABLES]
    jobs.append(("dq.rule_log", "dq_rule_log.csv"))
    for table, fname in jobs:
        df = _tidy(con.execute(f"SELECT * FROM {table}").df())
        df.to_csv(out_dir / fname, index=False, encoding="utf-8")
        counts[fname] = len(df)
    return counts


EXPORT_DESCRIPTIONS = {
    "mart_monthly.csv": "One row per month: revenue, returns, orders, active and new customers, orders per customer, revenue per order, growth, seasonality index.",
    "mart_yoy_decomposition.csv": "Year-on-year change in identified-customer revenue split into customers, orders per customer and revenue per order.",
    "mart_daily_revenue.csv": "One row per calendar day with 7 and 28 day averages and cumulative revenue.",
    "mart_orders.csv": "One row per invoice (sale or return) with date, month, customer, country, units and value. The base table for any date and country filter.",
    "mart_customers.csv": "One row per identified customer: first and last order, orders, revenue, order value, revenue rank and decile.",
    "mart_cohorts.csv": "Cohort by month offset by country: cohort size, active customers, retention rate, revenue.",
    "mart_rfm.csv": "Live RFM segmentation (1 December 2011) for each identified customer.",
    "mart_rfm_backtest.csv": "RFM segmentation at five past snapshots with what each customer did in the next 3 months.",
    "mart_rfm_summary.csv": "One row per segment: customers, revenue share, measured lapse rates and revenue at risk.",
    "mart_segment_targeting.csv": "Revenue at risk per customer by segment and whether the segment is targeted.",
    "mart_scenario_assumptions.csv": "The three assumed lapse reductions. These are assumptions, not measurements.",
    "mart_scenario.csv": "Revenue protected under each assumption. A scenario, not a result.",
    "mart_scenario_segments.csv": "The same scenario split by segment.",
    "mart_scenario_inputs.csv": "Size of the base, revenue at risk and the other inputs the memo quotes.",
    "mart_products.csv": "All-time product ranking with return rate and cumulative revenue share.",
    "mart_product_months_app.csv": "Product by month by country (top 500 products, the rest grouped as OTHER).",
    "mart_countries.csv": "Country ranking with year-on-year growth.",
    "dq_rule_log.csv": "Every data-quality rule with rows and revenue affected and the decision taken.",
}


def write_export_readme(out_dir: Path, counts: dict[str, int]) -> None:
    lines = [
        "# Exports",
        "",
        "Flat CSV files (UTF-8, header row) written by `retail export` from the DuckDB mart tables, for rebuilding the dashboard",
        "in Tableau Public or Power BI. Revenue is net of returns and is not profit. Money is rounded to 2 decimals and rates to 4.",
        "Definitions: [docs/KPI_DEFINITIONS.md](../docs/KPI_DEFINITIONS.md). Source data: UCI Online Retail II, CC BY 4.0.",
        "",
        "| File | Rows | Contents |",
        "|---|---:|---|",
    ]
    for name, n in counts.items():
        lines.append(f"| `{name}` | {n:,} | {EXPORT_DESCRIPTIONS.get(name, '')} |")
    text = chr(10).join(lines) + chr(10)
    (out_dir / "README.md").write_text(text, encoding="utf-8")
