"""A small synthetic stand-in for the flattened Online Retail II file, used by tests and CI.

It has the same text schema as `data/interim/online_retail_ii_text.csv` and deliberately
contains every kind of dirty row the SQL must handle: two sheets that overlap, exact
duplicates, cancellations, guest checkouts, postage and fee lines, zero prices, stock
write-offs, an order that is reversed the next day, mixed-case stock codes and a customer
who appears under two countries. It is made-up data. Nothing in the project's reported
results comes from it.
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import numpy as np

from retail import config as C

START = dt.date(2009, 12, 1)
END = dt.date(2011, 12, 9)
OVERLAP_START = dt.date(2010, 12, 1)
OVERLAP_END = dt.date(2010, 12, 9)
SHEET_1 = "Year 2009-2010"
SHEET_2 = "Year 2010-2011"
COUNTRIES = ["United Kingdom"] * 8 + ["Germany", "France", "EIRE", "Netherlands"]
NON_MERCH = [
    ("POST", "POSTAGE", 18.0),
    ("DOT", "DOTCOM POSTAGE", 25.0),
    ("M", "Manual", 12.0),
    ("BANK CHARGES", "Bank Charges", 15.0),
    ("gift_0001_20", "Dotcomgiftshop Gift Voucher 20.00", 16.67),
    ("TEST001", "This is a test product.", 4.0),
    ("ADJUST", "Adjustment by Peter", 30.0),
]


def _months(start: dt.date, end: dt.date) -> list[dt.date]:
    out, d = [], dt.date(start.year, start.month, 1)
    while d <= end:
        out.append(d)
        d = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def generate(path: Path, seed: int = 7, n_customers: int = 260) -> Path:
    """Write the fixture CSV and return its path. Deterministic for a given seed."""
    rng = np.random.default_rng(seed)
    products = [
        (f"{20000 + i}{'A' if i % 7 == 0 else ''}", f"PRODUCT NUMBER {i} ", round(float(p), 2))
        for i, p in enumerate(rng.choice([0.42, 0.85, 1.25, 1.65, 2.55, 4.95, 7.95], size=60))
    ]
    product_codes = {p[0] for p in products}
    months = _months(START, END)
    customers = []
    for i in range(n_customers):
        kind = rng.choice(["heavy", "medium", "light"], p=[0.15, 0.35, 0.50])
        start_idx = int(min(rng.exponential(5.0), len(months) - 1))
        life = int(rng.integers(2, 26)) if kind != "heavy" else int(rng.integers(12, 26))
        country = COUNTRIES[int(rng.integers(0, len(COUNTRIES)))]
        customers.append(
            {
                "id": 12000 + i,
                "p": {"heavy": 0.65, "medium": 0.30, "light": 0.12}[kind],
                "start": start_idx,
                "end": start_idx + life,
                "country": country,
                "alt_country": "Spain" if i == 3 else None,
            }
        )

    rows: list[tuple] = []  # (invoice, stock, desc, qty, ts, price, cust, country, date)
    inv = 489434

    def ts_on(day: dt.date) -> dt.datetime:
        return dt.datetime.combine(day, dt.time(int(rng.integers(8, 17)), int(rng.integers(0, 60))))

    def make_order(day: dt.date, cust: int | None, country: str, big: bool = False):
        nonlocal inv
        inv += 1
        invoice, stamp = str(inv), ts_on(day)
        lines = []
        for _ in range(int(rng.integers(1, 7))):
            code, desc, price = products[int(rng.integers(0, len(products)))]
            qty = int(np.clip(rng.lognormal(2.0, 0.8), 1, 400))
            lines.append((invoice, code, desc, qty, stamp, price, cust, country))
        if rng.random() < 0.12:
            code, desc, price = NON_MERCH[int(rng.integers(0, len(NON_MERCH)))]
            lines.append((invoice, code, desc, 1, stamp, price, cust, country))
        if rng.random() < 0.03:
            lines.append((invoice, "22423", None, 2, stamp, 0.0, None, country))  # free item
        if big:
            lines.append(
                (
                    invoice,
                    "23166",
                    "MEDIUM CERAMIC TOP STORAGE JAR",
                    6000,
                    stamp,
                    1.04,
                    cust,
                    country,
                )
            )
        out = list(lines)
        for ln in lines:
            if rng.random() < 0.02:
                out.append(ln)  # exact duplicate line
        for ln in out:
            rows.append((*ln, day))
        if big or (cust is not None and rng.random() < 0.04):
            inv += 1
            cday = day + dt.timedelta(days=1)
            cstamp = ts_on(cday)
            if big:  # the whole oversized line is reversed the next day
                cancelled = [(ln, ln[3]) for ln in lines if ln[3] == 6000]
            else:
                merch = [ln for ln in lines if ln[1] in product_codes]
                cancelled = [(ln, max(1, ln[3] // 2)) for ln in merch[:2]]
            for ln, q in cancelled:
                rows.append((f"C{inv}", ln[1], ln[2], -q, cstamp, ln[5], cust, country, cday))

    for day_offset in range((END - START).days + 1):
        day = START + dt.timedelta(days=day_offset)
        if day.weekday() == 5:  # no Saturday trading, as in the real file
            continue
        m_idx = (day.year - START.year) * 12 + day.month - START.month
        season = 1.5 if day.month in (9, 10, 11) else 0.9
        for c in customers:
            if not (c["start"] <= m_idx <= c["end"]):
                continue
            first_day = m_idx == c["start"] and day.day <= 28 and rng.random() < 0.05
            if first_day or rng.random() < c["p"] * season / 22.0:
                country = (
                    c["alt_country"] if (c["alt_country"] and rng.random() < 0.2) else c["country"]
                )
                make_order(day, c["id"], country)
        for _ in range(int(rng.poisson(0.9 * season))):  # guest checkouts
            make_order(day, None, "United Kingdom")
        if rng.random() < 0.01:  # stock write-off: negative quantity, price 0, no customer
            inv += 1
            rows.append(
                (
                    str(inv),
                    "22423",
                    "damaged",
                    -int(rng.integers(1, 40)),
                    ts_on(day),
                    0.0,
                    None,
                    "United Kingdom",
                    day,
                )
            )
        if rng.random() < 0.03:
            inv += 1
            rows.append(
                (str(inv), "m", "Manual ", 1, ts_on(day), 50.0, None, "United Kingdom", day)
            )

    make_order(dt.date(2010, 6, 8), 12010, "United Kingdom", big=True)  # reversed next day

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sheet", *C.RAW_COLUMNS])
        for r in sorted(rows, key=lambda r: (r[4], r[0])):
            invoice, code, desc, qty, stamp, price, cust, country, day = r
            cells = [
                invoice,
                code,
                desc if desc is not None else "",
                qty,
                stamp.strftime("%Y-%m-%d %H:%M:%S"),
                repr(price) if price != int(price) else str(int(price)),
                "" if cust is None else cust,
                country,
            ]
            in_overlap = OVERLAP_START <= day <= OVERLAP_END
            if day < OVERLAP_START or in_overlap:
                w.writerow([SHEET_1, *cells])
        for r in sorted(rows, key=lambda r: (r[4], r[0])):
            invoice, code, desc, qty, stamp, price, cust, country, day = r
            cells = [
                invoice,
                code,
                desc if desc is not None else "",
                qty,
                stamp.strftime("%Y-%m-%d %H:%M:%S"),
                repr(price) if price != int(price) else str(int(price)),
                "" if cust is None else cust,
                country,
            ]
            if day >= OVERLAP_START:
                w.writerow([SHEET_2, *cells])
    return path
