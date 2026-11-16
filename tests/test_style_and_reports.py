"""House rules (no em dashes, no hand-typed numbers in generated docs) and the report code."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from retail import config as C
from retail import plots, report, results

EM_DASH = chr(0x2014)  # spelled this way so this file itself stays free of the character
TEXT_SUFFIXES = {".md", ".py", ".sql", ".yml", ".yaml", ".toml", ".ipynb", ".txt", ".json", ".cfg"}
SKIP_DIRS = {
    ".venv",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "data",
    "__pycache__",
    "retail_sql_dashboard.egg-info",
    ".ipynb_checkpoints",
}


def repo_text_files():
    for path in C.ROOT.rglob("*"):
        if (
            path.is_file()
            and path.suffix in TEXT_SUFFIXES
            and not (set(path.relative_to(C.ROOT).parts) & SKIP_DIRS)
        ):
            yield path


def test_no_em_dashes_anywhere_in_the_repo():
    offenders = [
        str(p.relative_to(C.ROOT))
        for p in repo_text_files()
        if EM_DASH in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == []


def test_resume_bullets_are_not_tracked():
    out = subprocess.run(
        ["git", "ls-files", "RESUME_BULLETS.md"], cwd=C.ROOT, capture_output=True, text=True
    )
    assert out.stdout.strip() == ""


@pytest.fixture(scope="module")
def res(fixture_con):
    return results.collect(fixture_con, fixture=True)


def test_results_are_json_serialisable(res, tmp_path):
    path = tmp_path / "r.json"
    results.write_json(res, path)
    assert json.loads(path.read_text(encoding="utf-8"))["fixture"] is True


def test_memo_is_built_from_results(res):
    memo = report.memo_md(res)
    si = res["scenario_inputs"]
    assert f"{si['targeted_customers']:,.0f}" in memo
    assert plots.gbp(si["total_revenue_at_risk"]) in memo
    for low_high in res["scenario"]:
        assert plots.gbp(low_high["recovered_revenue"]) in memo
    assert "not a result" in memo and "assumption" in memo.lower()
    assert "not profit" in memo
    assert "Fixture run" in memo  # a fixture memo must never pass for the real one
    assert EM_DASH not in memo


def test_results_and_data_quality_docs_render(res):
    text = report.results_md(res) + report.dq_md(res)
    assert EM_DASH not in text
    assert "Revenue bridge" in text
    assert f"{res['headline']['raw_rows']:,}" in text


def test_readme_headline_block_is_replaced_in_place(res, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        f"intro\n{report.HEADLINE_START}\nold\n{report.HEADLINE_END}\noutro\n", encoding="utf-8"
    )
    assert report.update_readme(readme, res)
    text = readme.read_text(encoding="utf-8")
    assert "STALE_TEXT" not in text and text.startswith("intro") and text.endswith("outro\n")
    assert f"{res['headline']['raw_rows']:,}" in text


def test_figures_render(res, tmp_path):
    out = plots.all_figures(res, tmp_path)
    assert len(out) == 7 and all(Path(p).stat().st_size > 5000 for p in out.values())


def test_committed_results_match_the_committed_readme():
    """If the real results are committed, the README headline must show the same numbers."""
    path = C.RESULTS_DIR / "results.json"
    readme = C.ROOT / "README.md"
    if not path.exists() or not readme.exists():
        pytest.skip("no committed results yet")
    real = results.load_json(path)
    if real.get("fixture"):
        pytest.skip("results.json is a fixture run")
    block = re.search(
        re.escape(report.HEADLINE_START) + r"(.*?)" + re.escape(report.HEADLINE_END),
        readme.read_text(encoding="utf-8"),
        re.S,
    )
    assert block, "README has no headline block"
    assert (
        block.group(1).strip()
        == report.headline_block(real)
        .replace(report.HEADLINE_START, "")
        .replace(report.HEADLINE_END, "")
        .strip()
    )


def test_cli_fixture_run_all(tmp_path):
    """End to end through the command line on the synthetic file, as CI does."""
    out = tmp_path / "run"
    proc = subprocess.run(
        [sys.executable, "-m", "retail.cli", "run-all", "--fixture", "--out", str(out)],
        capture_output=True,
        text=True,
        cwd=C.ROOT,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    for rel in [
        "docs/RESULTS.md",
        "docs/MEMO.md",
        "docs/DATA_QUALITY.md",
        "docs/results/results.json",
        "exports/mart_orders.csv",
        "exports/mart_rfm_summary.csv",
        "retail.duckdb",
    ]:
        assert (out / rel).exists(), rel
