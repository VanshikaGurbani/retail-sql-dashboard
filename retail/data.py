"""Download, verify and flatten the raw Online Retail II workbook.

The downloaded zip and the extracted workbook are never modified. The only derived file is
`data/interim/online_retail_ii_text.csv`, which holds every cell as text exactly as the
workbook stores it (plus the sheet name), so that all typing and cleaning happens in SQL.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import zipfile
from pathlib import Path

import requests

from retail import config as C

CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest() -> dict:
    return json.loads(C.MANIFEST_PATH.read_text(encoding="utf-8"))


def verify_raw() -> dict[str, bool]:
    """Compare the raw files on disk with the recorded SHA-256 values."""
    manifest = _load_manifest()
    out = {}
    for name, info in manifest["files"].items():
        path = C.RAW_DIR / name
        out[name] = path.exists() and sha256_file(path) == info["sha256"]
    return out


def fetch_data(force: bool = False) -> Path:
    """Download the UCI zip (about 46 MB), check its SHA-256, extract the workbook."""
    C.RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    zip_path = C.RAW_DIR / C.ZIP_NAME
    if force or not zip_path.exists():
        with requests.get(C.DATASET_URL, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(CHUNK):
                    f.write(chunk)
    got = sha256_file(zip_path)
    want = manifest["files"][C.ZIP_NAME]["sha256"]
    if got != want:
        raise RuntimeError(
            f"{C.ZIP_NAME} checksum mismatch: expected {want}, got {got}. "
            "The file at the source may have changed; do not use it until you have looked."
        )
    xlsx_path = C.RAW_DIR / C.XLSX_NAME
    if not xlsx_path.exists():
        with zipfile.ZipFile(zip_path) as z:
            z.extract(C.XLSX_NAME, C.RAW_DIR)
    if sha256_file(xlsx_path) != manifest["files"][C.XLSX_NAME]["sha256"]:
        raise RuntimeError(f"{C.XLSX_NAME} checksum mismatch after extraction")
    return xlsx_path


def _cell_text(v: object) -> str:
    """Render a workbook cell as text without changing its meaning."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def workbook_to_text_csv(xlsx: Path | None = None, out: Path | None = None) -> Path:
    """Flatten both sheets into one all-text CSV with a leading `sheet` column."""
    from python_calamine import CalamineWorkbook

    xlsx = xlsx or C.RAW_DIR / C.XLSX_NAME
    out = out or C.INTERIM_DIR / C.RAW_CSV_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    wb = CalamineWorkbook.from_path(str(xlsx))
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sheet", *C.RAW_COLUMNS])
        for sheet in wb.sheet_names:
            rows = wb.get_sheet_by_name(sheet).to_python()
            header = [str(h) for h in rows[0]]
            if header != C.RAW_COLUMNS:
                raise RuntimeError(f"unexpected header in sheet {sheet!r}: {header}")
            for row in rows[1:]:
                w.writerow([sheet, *[_cell_text(v) for v in row]])
    return out
