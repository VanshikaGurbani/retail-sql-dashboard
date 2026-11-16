"""Layer-to-layer reconciliation, keys and cleaning rules, checked on the SQL output."""

from __future__ import annotations

import pytest

TOL = 0.005  # money is DECIMAL(.,4); allow half a penny of float noise in sums

NON_MERCH_CODES = "'POST','DOT','C2','CARRIAGE','BANK CHARGES','AMAZONFEE','CRUK','M','D','S','B','ADJUST','ADJUST2'"


def scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def test_staging_keeps_every_raw_row(con):
    assert scalar(con, "SELECT count(*) FROM stg.transactions") == scalar(
        con, "SELECT count(*) FROM raw.online_retail"
    )


def test_typing_loses_no_values(con):
    """TRY_CAST must not turn a present raw value into NULL."""
    bad = scalar(
        con,
        """SELECT count(*) FROM stg.transactions s JOIN raw.online_retail r USING (raw_row_id)
           WHERE (r.quantity IS NOT NULL AND s.quantity IS NULL)
              OR (r.invoice_ts IS NOT NULL AND s.invoice_ts IS NULL)
              OR (r.unit_price IS NOT NULL AND s.unit_price IS NULL)
              OR (nullif(trim(r.customer_id), '') IS NOT NULL AND s.customer_id IS NULL)""",
    )
    assert bad == 0


def test_every_row_gets_one_verdict_and_rows_reconcile(con):
    raw = scalar(con, "SELECT count(*) FROM raw.online_retail")
    flagged = scalar(con, "SELECT count(*) FROM stg.transactions_flagged")
    kept = scalar(con, "SELECT count(*) FROM clean.lines")
    excluded = scalar(con, "SELECT sum(n_rows) FROM dq.rule_log WHERE kind = 'excluded'")
    assert flagged == raw
    assert kept + excluded == raw


def test_revenue_bridge_reconciles_to_raw(con):
    raw_rev = scalar(con, "SELECT sum(quantity * unit_price) FROM stg.transactions")
    bridge = {
        r[0]: float(r[1])
        for r in con.execute("SELECT step, revenue FROM mart.revenue_bridge").fetchall()
    }
    assert bridge[0] == pytest.approx(float(raw_rev), abs=TOL)
    assert sum(bridge.values()) - bridge[99] == pytest.approx(bridge[99], abs=TOL)


def test_revenue_agrees_across_every_layer(con):
    kept = float(scalar(con, "SELECT sum(line_value) FROM clean.lines"))
    for sql in [
        "SELECT sum(order_value) FROM mart.orders",
        "SELECT sum(net_revenue) FROM mart.daily_revenue",
        "SELECT sum(net_revenue) FROM mart.monthly",
        "SELECT sum(net_revenue) FROM mart.product_months",
        "SELECT sum(net_revenue) FROM mart.product_months_app",
        "SELECT sum(net_revenue) FROM mart.products",
        "SELECT sum(net_revenue) FROM mart.countries",
        "SELECT net_revenue FROM mart.headline",
        "SELECT net_revenue_year1 + net_revenue_year2 FROM mart.headline",
    ]:
        assert float(scalar(con, sql)) == pytest.approx(kept, abs=TOL), sql


def test_customer_revenue_reconciles_to_identified_orders(con):
    """Customer table = identified revenue, except returns from people with no sale in window."""
    identified = float(
        scalar(con, "SELECT sum(order_value) FROM mart.orders WHERE customer_id IS NOT NULL")
    )
    customers = float(scalar(con, "SELECT sum(net_revenue) FROM mart.customers"))
    returns_only = float(
        scalar(
            con,
            """SELECT coalesce(sum(order_value), 0) FROM mart.orders
               WHERE customer_id IS NOT NULL
                 AND customer_id NOT IN (SELECT customer_id FROM mart.customers)""",
        )
    )
    assert customers + returns_only == pytest.approx(identified, abs=TOL)


@pytest.mark.parametrize(
    "table,key",
    [
        ("raw.online_retail", "raw_row_id"),
        ("stg.transactions", "raw_row_id"),
        ("clean.lines", "raw_row_id"),
        ("mart.orders", "invoice_no"),
        ("mart.customers", "customer_id"),
        ("mart.daily_revenue", "date"),
        ("mart.monthly", "month"),
        ("mart.cohorts", "cohort_month, country, month_offset"),
        ("mart.rfm_snapshots", "snapshot_date, customer_id"),
        ("mart.rfm", "customer_id"),
        ("mart.rfm_summary", "segment"),
        ("mart.products", "stock_code"),
        ("mart.product_months", "month, country, stock_code"),
        ("mart.product_months_app", "month, country, stock_code"),
        ("mart.countries", "country"),
        ("mart.customer_months", "customer_id, month"),
    ],
)
def test_no_duplicate_keys(con, table, key):
    dupes = scalar(
        con, f"SELECT count(*) FROM (SELECT {key} FROM {table} GROUP BY ALL HAVING count(*) > 1)"
    )
    assert dupes == 0


def test_kept_lines_are_clean(con):
    assert (
        scalar(con, "SELECT count(*) FROM clean.lines WHERE unit_price <= 0 OR quantity = 0") == 0
    )
    assert (
        scalar(con, "SELECT count(*) FROM clean.lines WHERE (line_type = 'sale') <> (quantity > 0)")
        == 0
    )
    assert (
        scalar(
            con,
            "SELECT count(*) FROM clean.lines WHERE line_type = 'return' AND invoice_no NOT LIKE 'C%'",
        )
        == 0
    )
    assert (
        scalar(
            con,
            f"""SELECT count(*) FROM clean.lines
                WHERE stock_code IN ({NON_MERCH_CODES})
                   OR starts_with(stock_code, 'GIFT_0001_') OR starts_with(stock_code, 'TEST')""",
        )
        == 0
    )
    assert (
        scalar(
            con,
            """SELECT count(*) FROM clean.lines l, dq.params p
               WHERE l.invoice_ts < p.window_start OR l.invoice_ts >= p.window_end_excl""",
        )
        == 0
    )


def test_no_exact_duplicate_lines_survive(con):
    d = scalar(
        con,
        """SELECT count(*) FROM (
               SELECT 1 FROM clean.lines
               GROUP BY invoice_no, stock_code, description, quantity, invoice_ts, unit_price,
                        customer_id, country
               HAVING count(*) > 1)""",
    )
    assert d == 0


def test_sheet_overlap_is_removed(con):
    """No invoice keeps lines from both sheets."""
    both = scalar(
        con,
        """SELECT count(*) FROM (
               SELECT invoice_no FROM stg.transactions_flagged
               WHERE dq_reason IS NULL GROUP BY invoice_no HAVING count(DISTINCT sheet) > 1)""",
    )
    assert both == 0


def test_every_customer_has_one_country(con):
    assert (
        scalar(
            con,
            """SELECT count(*) FROM (SELECT customer_id FROM clean.lines
                                    WHERE customer_id IS NOT NULL
                                    GROUP BY 1 HAVING count(DISTINCT country) > 1)""",
        )
        == 0
    )


def test_cohorts_are_consistent(con):
    assert (
        scalar(
            con, "SELECT count(*) FROM mart.cohorts WHERE month_offset = 0 AND retention_rate <> 1"
        )
        == 0
    )
    assert (
        scalar(
            con, "SELECT count(*) FROM mart.cohorts WHERE retention_rate < 0 OR retention_rate > 1"
        )
        == 0
    )
    n_customers = scalar(con, "SELECT count(*) FROM mart.customers")
    assert (
        scalar(con, "SELECT sum(cohort_size) FROM mart.cohorts WHERE month_offset = 0")
        == n_customers
    )
    # a cohort's size is the same at every observable offset
    assert (
        scalar(
            con,
            """SELECT count(*) FROM (SELECT cohort_month, country FROM mart.cohorts
                                     GROUP BY 1, 2 HAVING count(DISTINCT cohort_size) > 1)""",
        )
        == 0
    )
    # no cell lies beyond the last complete month
    last = scalar(con, "SELECT max(month) FROM mart.monthly")
    assert (
        scalar(
            con,
            f"""SELECT count(*) FROM mart.cohorts
                WHERE date_add(cohort_month, INTERVAL (month_offset) MONTH) > DATE '{last}'""",
        )
        == 0
    )


def test_rfm_scores_and_segments(con):
    assert (
        scalar(
            con,
            """SELECT count(*) FROM mart.rfm_snapshots
               WHERE r_score NOT BETWEEN 1 AND 5 OR f_score NOT BETWEEN 1 AND 5
                  OR m_score NOT BETWEEN 1 AND 5""",
        )
        == 0
    )
    assert (
        scalar(
            con,
            "SELECT count(*) FROM mart.rfm_snapshots WHERE recency_days < 1 OR frequency < 1 OR segment IS NULL",
        )
        == 0
    )
    found = {
        r[0] for r in con.execute("SELECT DISTINCT segment FROM mart.rfm_snapshots").fetchall()
    }
    assert found <= {
        "Champions",
        "Loyal",
        "Recent, low frequency",
        "Cooling",
        "At risk, high frequency",
        "Dormant",
    }
    # outcomes are observed for back-tests only
    assert (
        scalar(
            con,
            "SELECT count(*) FROM mart.rfm_snapshots WHERE kind = 'backtest' AND bought_next_quarter IS NULL",
        )
        == 0
    )
    assert (
        scalar(
            con,
            "SELECT count(*) FROM mart.rfm_snapshots WHERE kind = 'current' AND bought_next_quarter IS NOT NULL",
        )
        == 0
    )
    # someone who did not buy again cannot have positive revenue in the outcome window
    assert (
        scalar(
            con,
            "SELECT count(*) FROM mart.rfm_snapshots WHERE bought_next_quarter = false AND next_quarter_net_revenue > 0",
        )
        == 0
    )


def test_rfm_summary_covers_the_live_base(con):
    assert scalar(con, "SELECT sum(customers) FROM mart.rfm_summary") == scalar(
        con, "SELECT count(*) FROM mart.rfm"
    )


def test_yoy_decomposition_adds_up(con):
    effects, total = con.execute(
        """SELECT sum(revenue_effect) FILTER (WHERE sort_order < 4),
                  sum(revenue_effect) FILTER (WHERE sort_order = 4)
           FROM mart.yoy_decomposition"""
    ).fetchone()
    assert float(effects) == pytest.approx(float(total), abs=0.01)


def test_scenario_arithmetic(con):
    rows = con.execute(
        "SELECT lapse_reduction, recovered_revenue, targeted_revenue_at_risk FROM mart.scenario"
    ).fetchall()
    assert rows
    for reduction, recovered, at_risk in rows:
        assert float(recovered) == pytest.approx(float(at_risk) * float(reduction), rel=1e-9)
    # revenue at risk can never exceed the quarterly run-rate of the base
    assert scalar(
        con, "SELECT total_revenue_at_risk <= base_quarterly_run_rate FROM mart.scenario_inputs"
    )


def test_rule_log_is_complete(con):
    rows = con.execute("SELECT n_rows, decision, share_of_raw_rows FROM dq.rule_log").fetchall()
    assert rows
    assert all(n >= 0 and d and 0 <= s <= 1 for n, d, s in rows)
