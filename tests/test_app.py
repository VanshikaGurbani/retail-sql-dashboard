"""The dashboard's queries and the Streamlit page, run on the fixture exports."""

from __future__ import annotations

import datetime as dt

import pytest

from retail import appdata
from retail import config as C


@pytest.fixture()
def app_con(fixture_exports):
    return appdata.connect(fixture_exports)


def test_kpis_for_the_full_range_equal_the_headline(app_con, fixture_con):
    lo, hi, countries = appdata.bounds(app_con)
    k = appdata.query(app_con, "q1_kpis", start=lo, end=hi, countries=countries).iloc[0]
    head = fixture_con.execute("SELECT net_revenue, orders FROM mart.headline").fetchone()
    assert k.net_revenue == pytest.approx(float(head[0]), abs=0.05)
    assert k.orders == head[1]


def test_country_filter_changes_and_partitions_revenue(app_con):
    lo, hi, countries = appdata.bounds(app_con)
    whole = (
        appdata.query(app_con, "q1_kpis", start=lo, end=hi, countries=countries).iloc[0].net_revenue
    )
    parts = sum(
        appdata.query(app_con, "q1_kpis", start=lo, end=hi, countries=[c]).iloc[0].net_revenue
        for c in countries
    )
    assert parts == pytest.approx(whole, abs=0.05)
    one = (
        appdata.query(app_con, "q1_kpis", start=lo, end=hi, countries=countries[:1])
        .iloc[0]
        .net_revenue
    )
    assert one < whole


def test_date_filter_splits_revenue(app_con):
    lo, hi, countries = appdata.bounds(app_con)
    cut = dt.date(2010, 12, 1)
    a = appdata.query(
        app_con, "q1_kpis", start=lo, end=cut - dt.timedelta(days=1), countries=countries
    ).iloc[0]
    b = appdata.query(app_con, "q1_kpis", start=cut, end=hi, countries=countries).iloc[0]
    whole = appdata.query(app_con, "q1_kpis", start=lo, end=hi, countries=countries).iloc[0]
    assert a.net_revenue + b.net_revenue == pytest.approx(whole.net_revenue, abs=0.05)


def test_cohort_and_segment_queries_return_rows(app_con):
    lo, hi, countries = appdata.bounds(app_con)
    coh = appdata.query(app_con, "q2_cohorts", start=lo, end=hi, countries=countries)
    assert len(coh) and coh.retention_rate.between(0, 1).all()
    seg = appdata.query(app_con, "q3_segments", countries=countries)
    assert len(seg) and seg.lapse_rate.between(0, 1).all()


def test_product_query_ranks_by_revenue(app_con):
    lo, hi, countries = appdata.bounds(app_con)
    p = appdata.query(app_con, "q1_products", start=lo, end=hi, countries=countries)
    assert p.net_revenue.is_monotonic_decreasing and "OTHER" not in set(p.stock_code)


def test_streamlit_page_runs_without_error(fixture_exports, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("RETAIL_EXPORT_DIR", str(fixture_exports))
    at = AppTest.from_file(str(C.ROOT / "app" / "streamlit_app.py"), default_timeout=120)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.metric) >= 9 and len(at.tabs) == 4
    # moving the scenario slider changes the scenario number but not the measured ones
    before = [m.value for m in at.metric]
    at.slider[0].set_value(30).run()
    after = [m.value for m in at.metric]
    assert not at.exception
    assert before[:-1] == after[:-1] and before[-1] != after[-1]
