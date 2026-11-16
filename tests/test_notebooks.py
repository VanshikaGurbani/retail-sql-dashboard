"""Static checks on the committed notebook: it must be a finished run on the real data.

Running it end to end is a separate CI step (`retail run-notebooks --fixture --out DIR`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

nbformat = pytest.importorskip("nbformat")

ROOT = Path(__file__).resolve().parent.parent
NB = ROOT / "notebooks" / "01_exploratory_analysis.ipynb"
EM_DASH = chr(0x2014)


@pytest.fixture(scope="module")
def notebook():
    return nbformat.read(NB, as_version=4)


def output_text(nb) -> str:
    parts = []
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        for out in cell.get("outputs", []):
            if out.output_type == "stream":
                parts.append(out.text)
            elif out.output_type in ("display_data", "execute_result"):
                parts.append(out.data.get("text/markdown", "") + out.data.get("text/plain", ""))
    return "\n".join(parts)


def test_every_code_cell_ran_without_error(notebook):
    code = [c for c in notebook.cells if c.cell_type == "code" and c.source.strip()]
    assert code
    for cell in code[1:]:  # the first cell only imports
        assert cell.get("outputs"), f"no output saved for: {cell.source[:60]!r}"
    errors = [o for c in code for o in c.get("outputs", []) if o.output_type == "error"]
    assert not errors


def test_notebook_has_the_required_sections(notebook):
    text = "\n".join(c.source for c in notebook.cells if c.cell_type == "markdown").lower()
    for needle in [
        "missing values",
        "distributions",
        "outliers",
        "returns",
        "duplicates",
        "what is weak",
    ]:
        assert needle in text, needle


def test_notebook_was_run_on_real_data_not_the_fixture(notebook):
    assert "Fixture run" not in output_text(notebook)


def test_notebook_has_no_em_dash_and_is_a_reasonable_size(notebook):
    assert EM_DASH not in NB.read_text(encoding="utf-8")
    assert NB.stat().st_size < 1_500_000


def test_reconciliation_numbers_match_the_database(notebook):
    import duckdb

    from retail import config as C

    if not C.DB_PATH.exists():
        pytest.skip("no local build to compare with")
    con = duckdb.connect(str(C.DB_PATH), read_only=True)
    raw, kept = con.execute(
        "SELECT (SELECT count(*) FROM raw.online_retail), (SELECT count(*) FROM clean.lines)"
    ).fetchone()
    m = re.search(r"Reconciled: ([\d,]+) raw rows = ([\d,]+) kept", output_text(notebook))
    assert m, "reconciliation sentence missing"
    assert int(m.group(1).replace(",", "")) == raw
    assert int(m.group(2).replace(",", "")) == kept
