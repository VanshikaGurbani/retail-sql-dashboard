"""Helpers for the notebook. Two modes, chosen by RETAIL_NOTEBOOK_MODE:

- real (default): the full DuckDB built by `retail run-all` (data/retail.duckdb).
- fixture: a small synthetic build in the system temp folder. CI uses this to prove the
  notebook runs end to end. Nothing it prints is a result.

Every number in the notebook comes from a SQL query or from code; none is typed into the text.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import pandas as pd

from retail import config as C
from retail import fixture, pipeline

MODE_ENV = "RETAIL_NOTEBOOK_MODE"
DB_ENV = "RETAIL_NOTEBOOK_DB"
FIXTURE_DIR = Path(tempfile.gettempdir()) / "retail_notebook_fixture_v1"
P = C.PALETTE


def mode() -> str:
    return os.environ.get(MODE_ENV, "real")


def apply_style() -> None:
    try:  # draw inline inside a kernel even if an import chose Agg
        from IPython import get_ipython

        shell = get_ipython()
        if shell is not None:
            shell.run_line_magic("matplotlib", "inline")
    except Exception:  # pragma: no cover - only matters outside Jupyter
        pass
    plt.rcParams.update(
        {
            "figure.dpi": 110,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
        }
    )


def connect() -> duckdb.DuckDBPyConnection:
    if mode() == "fixture":
        db = FIXTURE_DIR / "retail.duckdb"
        if not db.exists():
            csv_path = fixture.generate(FIXTURE_DIR / "fixture_text.csv")
            pipeline.build(csv_path, db).close()
        return duckdb.connect(str(db), read_only=True)
    db = Path(os.environ.get(DB_ENV, C.DB_PATH))
    if not db.exists():
        raise SystemExit("data/retail.duckdb not found. Run `retail run-all` first.")
    return duckdb.connect(str(db), read_only=True)


def sql(con: duckdb.DuckDBPyConnection, query: str) -> pd.DataFrame:
    df = con.execute(query).df()
    for col in df.columns:
        if (
            str(df[col].dtype) == "object"
            and len(df)
            and df[col].map(lambda v: v.__class__.__name__ == "Decimal").any()
        ):
            df[col] = df[col].astype("float64")
    return df


def banner() -> None:
    from IPython.display import Markdown, display

    if mode() == "fixture":
        display(
            Markdown(
                "> **Fixture run.** This notebook is running on a small synthetic file so CI can "
                "prove it works. The numbers below are not results."
            )
        )
