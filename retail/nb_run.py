"""Execute the notebooks in `notebooks/` and save them with outputs.

    retail run-notebooks                       real data, outputs saved in place
    retail run-notebooks --fixture --out DIR   synthetic fixture (what CI does); the executed
                                               copy goes to DIR/notebooks, the committed one is
                                               left untouched

Needs the optional `notebooks` extra (nbformat, nbclient, ipykernel).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from retail import config as C
from retail import nb as nbhelpers

NOTEBOOK_DIR = C.ROOT / "notebooks"


def notebook_paths(directory: Path = NOTEBOOK_DIR) -> list[Path]:
    return sorted(directory.glob("[0-9][0-9]_*.ipynb"))


def run_all(db_path: Path, fixture: bool = False, out: Path | None = None, timeout: int = 1800):
    try:
        import nbformat
        from nbclient import NotebookClient
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Running notebooks needs: pip install -e '.[notebooks]'") from exc
    if fixture and out is None:
        raise SystemExit("--fixture needs --out so the committed notebook is not overwritten")
    os.environ[nbhelpers.MODE_ENV] = "fixture" if fixture else "real"
    os.environ[nbhelpers.DB_ENV] = str(db_path)
    written = []
    for path in notebook_paths():
        started = time.time()
        nb = nbformat.read(path, as_version=4)
        NotebookClient(
            nb,
            timeout=timeout,
            kernel_name="python3",
            resources={"metadata": {"path": str(NOTEBOOK_DIR)}},
        ).execute()
        dest_dir = (Path(out) / "notebooks") if out is not None else NOTEBOOK_DIR
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / path.name
        nbformat.write(nb, dest)
        written.append(dest)
        print(f"{path.name}: ok in {time.time() - started:.0f}s -> {dest}", flush=True)
    return written
