"""Command line entry point: `retail <command>`."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from retail import config as C


def _raw_csv(fixture: bool, out: Path | None) -> Path:
    if fixture:
        from retail import fixture as fx

        base = (out or Path(tempfile.gettempdir()) / "retail_fixture") / "interim"
        return fx.generate(base / C.FIXTURE_CSV_NAME)
    path = C.INTERIM_DIR / C.RAW_CSV_NAME
    if not path.exists():
        raise SystemExit("No flattened data found. Run `retail fetch-data` first.")
    return path


def cmd_fetch_data(args) -> None:
    from retail import data

    xlsx = data.fetch_data(force=args.force)
    print(f"raw workbook verified: {xlsx}")
    csv_path = data.workbook_to_text_csv()
    print(f"flattened to text: {csv_path}")


def cmd_verify_raw(args) -> None:
    from retail import data

    result = data.verify_raw()
    for name, ok in result.items():
        print(f"{'OK  ' if ok else 'FAIL'} {name}")
    if not all(result.values()):
        raise SystemExit(1)


def _paths(args):
    out = Path(args.out) if args.out else None
    if args.fixture and out is None:
        out = Path(tempfile.gettempdir()) / "retail_fixture"
    return C.run_paths(out), out


def cmd_build(args) -> None:
    from retail import pipeline

    paths, out = _paths(args)
    con = pipeline.build(_raw_csv(args.fixture, out), paths.db)
    n = con.execute("SELECT count(*) FROM clean.lines").fetchone()[0]
    print(f"built {paths.db} ({n:,} clean lines)")
    con.close()


def cmd_export(args) -> None:
    from retail import pipeline

    paths, _ = _paths(args)
    con = pipeline.connect(paths.db, read_only=True)
    counts = pipeline.export_marts(con, paths.exports)
    pipeline.write_export_readme(paths.exports, counts)
    con.close()
    for name, n in counts.items():
        print(f"{name}: {n:,} rows")


def cmd_report(args) -> None:
    from retail import pipeline, plots, report, results

    paths, _ = _paths(args)
    con = pipeline.connect(paths.db, read_only=True)
    res = results.collect(con, fixture=args.fixture)
    con.close()
    results.write_json(res, paths.results_json)
    plots.all_figures(res, paths.figures)
    (paths.docs / "RESULTS.md").write_text(report.results_md(res), encoding="utf-8")
    (paths.docs / "MEMO.md").write_text(report.memo_md(res), encoding="utf-8")
    (paths.docs / "DATA_QUALITY.md").write_text(report.dq_md(res), encoding="utf-8")
    if not args.fixture and report.update_readme(C.ROOT / "README.md", res):
        print("README headline block updated")
    print(f"wrote reports and figures under {paths.docs}")


def cmd_run_notebooks(args) -> None:
    from retail import nb_run

    paths, _ = _paths(args)
    nb_run.run_all(paths.db, fixture=args.fixture, out=Path(args.out) if args.out else None)


def cmd_run_all(args) -> None:
    cmd_build(args)
    cmd_export(args)
    cmd_report(args)
    if args.notebooks:
        cmd_run_notebooks(args)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="retail", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, func, help_: str, fixture: bool = True):
        p = sub.add_parser(name, help=help_)
        p.set_defaults(func=func)
        if fixture:
            p.add_argument("--fixture", action="store_true", help="use the small synthetic file")
            p.add_argument(
                "--out", help="write everything under this directory instead of the repo"
            )
        return p

    p = add(
        "fetch-data",
        cmd_fetch_data,
        "download, checksum and flatten the raw workbook",
        fixture=False,
    )
    p.add_argument("--force", action="store_true", help="download again even if the zip exists")
    add("verify-raw", cmd_verify_raw, "check raw files against the recorded SHA-256", fixture=False)
    add("build", cmd_build, "run the SQL files into DuckDB")
    add("export", cmd_export, "write mart tables to CSV")
    add("report", cmd_report, "write results.json, figures, RESULTS.md, MEMO.md, DATA_QUALITY.md")
    add("run-notebooks", cmd_run_notebooks, "execute the notebook and save outputs")
    p = add("run-all", cmd_run_all, "build, export and report (and notebooks with --notebooks)")
    p.add_argument("--notebooks", action="store_true")

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
