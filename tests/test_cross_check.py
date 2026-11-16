"""Re-implement the cleaning rules in pandas, straight from the flattened raw file, and check
the SQL layer produces the same row counts and revenue. If the SQL and this independent code
agree, a mistake would have to be made the same way twice."""

from __future__ import annotations

import pandas as pd
import pytest

NON_MERCH = {
    "POST", "DOT", "C2", "CARRIAGE", "BANK CHARGES", "AMAZONFEE", "CRUK",
    "M", "D", "S", "B", "ADJUST", "ADJUST2",
}  # fmt: skip


def pandas_verdicts(csv_path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    df["invoice_no"] = df["Invoice"].str.strip()
    df["is_cancel"] = df["invoice_no"].str.upper().str.startswith("C")
    df["stock"] = df["StockCode"].str.strip().str.upper()
    df["desc"] = df["Description"].str.strip()
    df["qty"] = pd.to_numeric(df["Quantity"], errors="coerce")
    df["ts"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")
    df["price_i"] = (pd.to_numeric(df["Price"], errors="coerce") * 10000).round()
    df["cust"] = df["Customer ID"].str.strip()
    df["ctry"] = df["Country"].str.strip()
    df["value_i"] = df["qty"] * df["price_i"]  # in 1/10000 of a pound, exact for the data

    last_sheet = df.groupby("invoice_no")["sheet"].transform("max")
    n_sheets = df.groupby("invoice_no")["sheet"].transform("nunique")
    overlap = (n_sheets > 1) & (df["sheet"] == last_sheet)
    keys = ["invoice_no", "stock", "desc", "qty", "ts", "price_i", "cust", "ctry"]
    dup = pd.Series(False, index=df.index)
    dup[~overlap] = df[~overlap].duplicated(subset=keys, keep="first")
    non_merch = (
        df["stock"].isin(NON_MERCH)
        | df["stock"].str.startswith("GIFT_0001_")
        | df["stock"].str.startswith("TEST")
    )
    bad_value = df["qty"].isna() | df["ts"].isna() | df["price_i"].isna() | (df["qty"] == 0)
    sign = df["is_cancel"] != (df["qty"] < 0)
    price = df["price_i"] <= 0
    window = (df["ts"] < pd.Timestamp("2009-12-01")) | (df["ts"] >= pd.Timestamp("2011-12-01"))

    reason = pd.Series("", index=df.index)
    for name, mask in [  # first match wins, same order as sql/20_dq_flags.sql
        ("cross_sheet_overlap_copy", overlap),
        ("exact_duplicate_line", dup),
        ("non_merchandise_charge", non_merch),
        ("unparseable_or_zero_quantity", bad_value),
        ("sign_conflict", sign),
        ("nonpositive_price", price),
        ("outside_analysis_window", window),
    ]:
        reason[(reason == "") & mask] = name
    df["reason"] = reason
    return df


def test_cleaning_matches_independent_pandas_implementation(source):
    con, csv_path = source
    df = pandas_verdicts(csv_path)
    sql_counts = dict(
        con.execute("SELECT rule, n_rows FROM dq.rule_log WHERE kind = 'excluded'").fetchall()
    )
    py_counts = df[df.reason != ""].groupby("reason").size().to_dict()
    for rule, n in sql_counts.items():
        assert py_counts.get(rule, 0) == n, rule
    kept = df[df.reason == ""]
    assert len(kept) == con.execute("SELECT count(*) FROM clean.lines").fetchone()[0]
    sql_rev = float(con.execute("SELECT sum(line_value) FROM clean.lines").fetchone()[0])
    assert kept["value_i"].sum() / 10000 == pytest.approx(sql_rev, abs=0.01)
    # headline total independent of every SQL mart
    assert float(
        con.execute("SELECT net_revenue FROM mart.headline").fetchone()[0]
    ) == pytest.approx(kept["value_i"].sum() / 10000, abs=0.01)


def test_raw_revenue_matches_the_file_itself(source):
    """The bridge's starting point equals quantity x price summed straight from the CSV."""
    con, csv_path = source
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    total = (
        pd.to_numeric(df["Quantity"]) * (pd.to_numeric(df["Price"]) * 10000).round()
    ).sum() / 10000
    bridge0 = float(
        con.execute("SELECT revenue FROM mart.revenue_bridge WHERE step = 0").fetchone()[0]
    )
    assert bridge0 == pytest.approx(total, abs=0.01)
    assert con.execute("SELECT count(*) FROM raw.online_retail").fetchone()[0] == len(df)
