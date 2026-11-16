"""Shared fixtures. SQL tests run on the synthetic fixture (always) and on the full Online
Retail II build (when data/retail.duckdb exists locally, as it does after `retail run-all`)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from retail import config as C
from retail import fixture, pipeline


@pytest.fixture(scope="session")
def fixture_csv(tmp_path_factory) -> Path:
    return fixture.generate(tmp_path_factory.mktemp("fx") / "fixture_text.csv")


@pytest.fixture(scope="session")
def fixture_con(fixture_csv):
    con = pipeline.build(fixture_csv)
    yield con
    con.close()


@pytest.fixture(scope="session")
def fixture_exports(fixture_con, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("exports")
    pipeline.export_marts(fixture_con, out)
    return out


@pytest.fixture(scope="session")
def real_con():
    if not C.DB_PATH.exists():
        pytest.skip("full build not present (run `retail run-all`)")
    con = duckdb.connect(str(C.DB_PATH), read_only=True)
    yield con
    con.close()


@pytest.fixture(params=["fixture", pytest.param("real", marks=pytest.mark.real)])
def con(request):
    """The same SQL test runs against the fixture and, locally, against the real build."""
    return request.getfixturevalue("fixture_con" if request.param == "fixture" else "real_con")


@pytest.fixture(params=["fixture", pytest.param("real", marks=pytest.mark.real)])
def source(request):
    """(connection, flattened raw csv path) pairs for cross-implementation checks."""
    if request.param == "fixture":
        return request.getfixturevalue("fixture_con"), request.getfixturevalue("fixture_csv")
    csv_path = C.INTERIM_DIR / C.RAW_CSV_NAME
    if not csv_path.exists():
        pytest.skip("flattened raw csv not present")
    return request.getfixturevalue("real_con"), csv_path
