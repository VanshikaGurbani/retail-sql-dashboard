"""Paths and constants shared by the pipeline, the tests and the app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
EXPORT_DIR = ROOT / "exports"
DOCS_DIR = ROOT / "docs"
FIG_DIR = DOCS_DIR / "figures"
RESULTS_DIR = DOCS_DIR / "results"
MANIFEST_PATH = ROOT / "manifest" / "online_retail_ii_sha256.json"

DB_PATH = DATA_DIR / "retail.duckdb"
FIXTURE_CSV_NAME = "fixture_text.csv"

# UCI Machine Learning Repository, dataset 502 (Online Retail II), licence CC BY 4.0.
DATASET_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
ZIP_NAME = "online_retail_ii.zip"
XLSX_NAME = "online_retail_II.xlsx"
RAW_CSV_NAME = "online_retail_ii_text.csv"

# Column names of the two Excel sheets, in order.
RAW_COLUMNS = [
    "Invoice",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "Price",
    "Customer ID",
    "Country",
]

# Mart tables written to exports/ as CSV (name in DuckDB is mart.<name>, file is mart_<name>.csv).
EXPORT_TABLES = [
    "monthly",
    "yoy_decomposition",
    "daily_revenue",
    "orders",
    "customers",
    "cohorts",
    "rfm",
    "rfm_backtest",
    "rfm_summary",
    "segment_targeting",
    "scenario_assumptions",
    "scenario",
    "scenario_segments",
    "scenario_inputs",
    "products",
    "product_months_app",
    "countries",
]

# Colour-blind safe palette (Okabe and Ito, 2008).
PALETTE = {
    "blue": "#0072B2",
    "orange": "#E69F00",
    "green": "#009E73",
    "vermillion": "#D55E00",
    "sky": "#56B4E9",
    "purple": "#CC79A7",
    "yellow": "#F0E442",
    "grey": "#7F7F7F",
}


@dataclass(frozen=True)
class RunPaths:
    """Where one run reads and writes. Real runs use the repo; fixture runs use a scratch dir."""

    db: Path
    exports: Path
    docs: Path

    @property
    def figures(self) -> Path:
        return self.docs / "figures"

    @property
    def results_json(self) -> Path:
        return self.docs / "results" / "results.json"


def run_paths(out: Path | None = None) -> RunPaths:
    """Repo locations by default, or a self-contained directory when `out` is given."""
    if out is None:
        return RunPaths(db=DB_PATH, exports=EXPORT_DIR, docs=DOCS_DIR)
    out = Path(out)
    return RunPaths(db=out / "retail.duckdb", exports=out / "exports", docs=out / "docs")
