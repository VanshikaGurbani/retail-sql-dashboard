"""Read the finished marts into one JSON-serialisable dict. No number is computed by hand:
everything here is a SELECT from a mart table, apart from Wilson intervals on counts."""

from __future__ import annotations

import datetime as dt
import decimal
import json
import math
from pathlib import Path

import duckdb

from retail import config as C


def _clean(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):
        return _clean(v.item())
    return v


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [{c: _clean(v) for c, v in zip(cols, r)} for r in cur.fetchall()]


def one(con: duckdb.DuckDBPyConnection, sql: str) -> dict:
    return rows(con, sql)[0]


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (centre - half, centre + half)


def collect(con: duckdb.DuckDBPyConnection, fixture: bool = False) -> dict:
    res: dict = {"fixture": fixture}
    res["headline"] = one(con, "SELECT * FROM mart.headline")
    res["bridge"] = rows(con, "SELECT * FROM mart.revenue_bridge ORDER BY step")
    res["dq"] = rows(con, "SELECT * FROM dq.rule_log ORDER BY rule_order")
    res["monthly"] = rows(con, "SELECT * FROM mart.monthly ORDER BY month")
    res["yoy"] = rows(con, "SELECT * FROM mart.yoy_decomposition ORDER BY sort_order")
    res["countries"] = rows(con, "SELECT * FROM mart.countries ORDER BY revenue_rank LIMIT 10")
    res["products"] = rows(con, "SELECT * FROM mart.products ORDER BY revenue_rank LIMIT 10")
    res["high_return_products"] = rows(
        con,
        """SELECT stock_code, description, sales_revenue, returns_value, return_rate
           FROM mart.products WHERE sales_revenue >= 20000 ORDER BY return_rate DESC LIMIT 5""",
    )
    res["retention_curve"] = rows(con, "SELECT * FROM mart.retention_curve ORDER BY month_offset")
    res["cohort_grid"] = rows(
        con,
        """SELECT cohort_month, month_offset, sum(cohort_size) AS cohort_size,
                  sum(active_customers) AS active_customers
           FROM mart.cohorts GROUP BY ALL ORDER BY cohort_month, month_offset""",
    )
    segs = rows(con, "SELECT * FROM mart.rfm_summary")
    targeting = {r["segment"]: r for r in rows(con, "SELECT * FROM mart.segment_targeting")}
    for s in segs:
        lo, hi = wilson(s["same_season_repurchasers"] or 0, s["same_season_customers"] or 0)
        s["repurchase_ci_low"], s["repurchase_ci_high"] = lo, hi
        s["lapse_ci_low"], s["lapse_ci_high"] = 1 - hi, 1 - lo
        t = targeting.get(s["segment"], {})
        s["is_targeted"] = t.get("is_targeted")
        s["at_risk_per_customer"] = t.get("at_risk_per_customer")
        s["share_of_total_at_risk"] = t.get("share_of_total_at_risk")
    res["segments"] = segs
    res["scenario"] = rows(con, "SELECT * FROM mart.scenario ORDER BY lapse_reduction")
    res["scenario_segments"] = rows(
        con,
        "SELECT * FROM mart.scenario_segments ORDER BY lapse_reduction, revenue_at_risk_next_quarter DESC",
    )
    res["scenario_inputs"] = one(con, "SELECT * FROM mart.scenario_inputs")
    res["snapshots"] = rows(con, "SELECT * FROM dq.snapshots ORDER BY snapshot_date")
    res["params"] = one(con, "SELECT * FROM dq.params")
    return res


def write_json(res: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(res, indent=2, default=_clean, ensure_ascii=False), encoding="utf-8")


def load_json(path: Path | None = None) -> dict:
    path = path or C.RESULTS_DIR / "results.json"
    return json.loads(path.read_text(encoding="utf-8"))
