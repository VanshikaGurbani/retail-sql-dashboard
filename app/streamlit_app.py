"""Retail retention dashboard: three questions that answer one business decision.

Reads only the CSV marts in exports/ (set RETAIL_EXPORT_DIR to point elsewhere) and runs the
SQL in sql/app/ against them. Colours are the Okabe-Ito colour-blind safe palette; every chart
has a plain-text takeaway and a data table behind it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retail import appdata  # noqa: E402
from retail.config import PALETTE as P  # noqa: E402

st.set_page_config(page_title="Retail retention dashboard", layout="wide")

BLUE, ORANGE, VERM, SKY, GREEN = P["blue"], P["orange"], P["vermillion"], P["sky"], P["green"]


def gbp(x: float) -> str:
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e6:
        return f"{sign}£{x / 1e6:.2f}M"
    if x >= 1e3:
        return f"{sign}£{x / 1e3:.0f}k"
    return f"{sign}£{x:.0f}"


@st.cache_resource
def get_con():
    return appdata.connect()


@st.cache_data
def get_bounds():
    lo, hi, countries = appdata.bounds(get_con())
    return lo, hi, countries


@st.cache_data
def run(name: str, start, end, countries: tuple[str, ...]) -> pd.DataFrame:
    return appdata.query(get_con(), name, start=start, end=end, countries=list(countries))


def chart_title(text: str) -> alt.TitleParams:
    return alt.TitleParams(text, anchor="start", fontSize=15, fontWeight="bold")


def show_table(df: pd.DataFrame, label: str = "Data behind this chart") -> None:
    with st.expander(label):
        st.dataframe(df, hide_index=True)


lo, hi, all_countries = get_bounds()

st.title("Which customers should next quarter's retention budget target?")
st.markdown(
    "A UK online gift-ware retailer, December 2009 to November 2011. Three questions, one decision. "
    "**Revenue here is net of returns and is not profit: the data has no costs or margins.**"
)

with st.sidebar:
    st.header("Filters")
    picked = st.date_input("Date range", value=(lo, hi), min_value=lo, max_value=hi)
    start, end = (
        (picked[0], picked[1]) if isinstance(picked, tuple) and len(picked) == 2 else (lo, hi)
    )
    countries = st.multiselect("Countries", all_countries, default=all_countries)
    if not countries:
        st.warning("Pick at least one country.")
        st.stop()
    st.caption(
        "Filters apply to questions 1 and 2. Question 3 is a snapshot on 1 December 2011, so only the country filter applies."
    )
    st.header("Scenario assumption")
    reduction_pct = st.slider(
        "Assumed cut in lapse rate for contacted customers (percent)",
        0,
        40,
        10,
        5,
        format="%d%%",
        help="Not measured: nothing in the data observes a campaign. A 10% cut turns a 60% lapse rate into 54%.",
    )
    reduction = reduction_pct / 100
    with st.expander("Data caveats", expanded=False):
        st.markdown(
            "- Revenue is **net of returns** and is **not profit**; there are no costs or margins.\n"
            "- **Guest checkouts** (no customer ID, about 13% of revenue) count in revenue but not in customer metrics.\n"
            "- Cohorts and segments cover **identified customers only**.\n"
            "- The first cohort (December 2009) is hidden: it includes customers who bought before the file starts.\n"
            "- December 2011 is cut off on the 9th, so it is excluded.\n"
            "- Many customers are wholesalers; a few accounts are very large.\n"
            "- Product tables keep the top 500 products and group the rest as OTHER."
        )

key = (start, end, tuple(countries))
tab1, tab2, tab3, tab4 = st.tabs(
    ["1. Revenue", "2. Retention", "3. Segments and risk", "Data caveats"]
)

# ---------------------------------------------------------------- Question 1
with tab1:
    k = run("q1_kpis", *key).iloc[0]
    monthly = run("q1_monthly", *key)
    span_days = (end - start).days + 1
    prev_end = pd.Timestamp(start) - pd.Timedelta(days=1)
    prev_start = prev_end - pd.Timedelta(days=span_days - 1)
    prev = None
    if prev_start.date() >= lo:
        prev = run("q1_kpis", prev_start.date(), prev_end.date(), key[2]).iloc[0]

    def delta(cur: float, old: float | None) -> str | None:
        if prev is None or not old:
            return None
        return f"{(cur / old - 1) * 100:+.1f}% vs previous {span_days} days"

    c = st.columns(5)
    c[0].metric(
        "Net revenue",
        gbp(k.net_revenue),
        delta(k.net_revenue, None if prev is None else prev.net_revenue),
    )
    c[1].metric(
        "Orders", f"{int(k.orders):,}", delta(k.orders, None if prev is None else prev.orders)
    )
    c[2].metric(
        "Active customers",
        f"{int(k.active_customers):,}",
        delta(k.active_customers, None if prev is None else prev.active_customers),
    )
    opc = k.orders_identified / k.active_customers if k.active_customers else 0
    c[3].metric("Orders per customer", f"{opc:.2f}")
    c[4].metric(
        "Return rate",
        f"{(-k.returns_value / k.sales_revenue * 100) if k.sales_revenue else 0:.1f}%",
    )

    if monthly.empty:
        st.info("No sales in this selection.")
    else:
        monthly["avg3"] = monthly.net_revenue.rolling(3, min_periods=1).mean()
        peak = monthly.loc[monthly.net_revenue.idxmax()]
        title = f"Net revenue peaks in {pd.Timestamp(peak.month):%B %Y} at {gbp(peak.net_revenue)}"
        base = alt.Chart(monthly).encode(
            x=alt.X("yearmonth(month):O", title="Month", axis=alt.Axis(labelAngle=-45))
        )
        bars = base.mark_bar(color=BLUE).encode(
            y=alt.Y("net_revenue:Q", title="Net revenue (£)", axis=alt.Axis(format="~s")),
            tooltip=[
                alt.Tooltip("yearmonth(month):O", title="Month"),
                alt.Tooltip("net_revenue:Q", format=",.0f", title="Net revenue (£)"),
            ],
        )
        line = base.mark_line(color=ORANGE, strokeWidth=3, point=True).encode(y="avg3:Q")
        st.altair_chart(
            (bars + line).properties(title=chart_title(title), height=320), width="stretch"
        )
        st.caption("Bars: net revenue per month. Orange line: 3-month average.")
        show_table(monthly.drop(columns="avg3"))

        st.subheader("What drives revenue: customers, how often they order, basket size")
        d = monthly.melt(
            id_vars="month",
            value_vars=["active_customers", "orders_per_customer", "revenue_per_order"],
            var_name="driver",
            value_name="value",
        )
        d["driver"] = d.driver.map(
            {
                "active_customers": "Active customers",
                "orders_per_customer": "Orders per customer",
                "revenue_per_order": "Net revenue per order (£)",
            }
        )
        driver_chart = (
            alt.Chart(d)
            .mark_line(point=True, color=BLUE, strokeWidth=2.5)
            .encode(
                x=alt.X("yearmonth(month):O", title="Month", axis=alt.Axis(labelAngle=-45)),
                y=alt.Y("value:Q", title=None, scale=alt.Scale(zero=False)),
            )
            .properties(height=170, width=300)
            .facet(facet=alt.Facet("driver:N", title=None), columns=3)
            .resolve_scale(y="independent")
        )
        st.altair_chart(driver_chart, width="stretch")
        st.caption("Net revenue for identified customers is the product of these three lines.")

        left, right = st.columns(2)
        products = run("q1_products", *key)
        if not products.empty:
            top = products.iloc[0]
            pchart = (
                alt.Chart(products)
                .mark_bar(color=BLUE)
                .encode(
                    y=alt.Y("description:N", sort="-x", title=None),
                    x=alt.X("net_revenue:Q", title="Net revenue (£)", axis=alt.Axis(format="~s")),
                    tooltip=[
                        "stock_code",
                        "description",
                        alt.Tooltip("net_revenue:Q", format=",.0f"),
                        alt.Tooltip("return_rate:Q", format=".1%"),
                    ],
                )
                .properties(
                    title=chart_title(
                        f"{top.description.title()} is the top product at {gbp(top.net_revenue)}"
                    ),
                    height=320,
                )
            )
            left.altair_chart(pchart, width="stretch")
            with left:
                show_table(products)
        countries_df = run("q1_countries", *key)
        if not countries_df.empty:
            share = countries_df.iloc[0].net_revenue / k.net_revenue if k.net_revenue else 0
            cchart = (
                alt.Chart(countries_df)
                .mark_bar(color=ORANGE)
                .encode(
                    y=alt.Y("country:N", sort="-x", title=None),
                    x=alt.X("net_revenue:Q", title="Net revenue (£)", axis=alt.Axis(format="~s")),
                    tooltip=["country", alt.Tooltip("net_revenue:Q", format=",.0f"), "customers"],
                )
                .properties(
                    title=chart_title(
                        f"{countries_df.iloc[0].country} is {share * 100:.0f}% of net revenue"
                    ),
                    height=320,
                )
            )
            right.altair_chart(cchart, width="stretch")
            with right:
                show_table(countries_df)

# ---------------------------------------------------------------- Question 2
with tab2:
    coh = run("q2_cohorts", *key)
    if coh.empty:
        st.info("No cohorts start in this selection.")
    else:
        curve = (
            coh.groupby("month_offset")
            .agg(cohort_size=("cohort_size", "sum"), active=("active_customers", "sum"))
            .reset_index()
        )
        curve["retention_rate"] = curve.active / curve.cohort_size
        m1 = curve[curve.month_offset == 1]
        headline = (
            f"{m1.retention_rate.iloc[0] * 100:.0f}% of new customers buy again the next month"
            if len(m1)
            else "Retention after the first month"
        )
        rchart = (
            alt.Chart(curve[curve.month_offset >= 1])
            .mark_line(color=BLUE, strokeWidth=3, point=True)
            .encode(
                x=alt.X("month_offset:Q", title="Months since first purchase"),
                y=alt.Y(
                    "retention_rate:Q", title="Share of cohort buying", axis=alt.Axis(format="%")
                ),
                tooltip=[
                    "month_offset",
                    alt.Tooltip("retention_rate:Q", format=".1%"),
                    "cohort_size",
                ],
            )
            .properties(title=chart_title(headline), height=280)
        )
        st.altair_chart(rchart, width="stretch")
        st.caption(
            "A customer joins the cohort of the month of their first purchase. Active means at least one purchase invoice in that month."
        )
        heat = coh[(coh.month_offset >= 1) & (coh.month_offset <= 12)]
        hchart = (
            alt.Chart(heat)
            .mark_rect()
            .encode(
                x=alt.X("month_offset:O", title="Months since first purchase"),
                y=alt.Y("yearmonth(cohort_month):O", title="Cohort (first purchase month)"),
                color=alt.Color(
                    "retention_rate:Q",
                    title="Retention",
                    scale=alt.Scale(scheme="cividis", domain=[0, 0.4]),
                    legend=alt.Legend(format="%"),
                ),
                tooltip=[
                    alt.Tooltip("yearmonth(cohort_month):O", title="Cohort"),
                    "month_offset",
                    alt.Tooltip("retention_rate:Q", format=".1%"),
                    "cohort_size",
                ],
            )
            .properties(
                title=chart_title(
                    "Retention by monthly cohort (darker means fewer customers came back)"
                ),
                height=420,
            )
        )
        st.altair_chart(hchart, width="stretch")
        show_table(coh)

# ---------------------------------------------------------------- Question 3
with tab3:
    seg = run("q3_segments", key[0], key[1], key[2])
    if seg.empty:
        st.info("No customers in this selection.")
    else:
        seg["targeted"] = seg.at_risk_per_customer > seg.revenue_at_risk.sum() / seg.customers.sum()
        tg = seg[seg.targeted]
        recovered = tg.revenue_at_risk.sum() * reduction
        top = seg.sort_values("revenue_share", ascending=False).iloc[0]
        c = st.columns(4)
        c[0].metric("Customers in selection", f"{int(seg.customers.sum()):,}")
        c[1].metric("Revenue at risk next quarter", gbp(seg.revenue_at_risk.sum()))
        c[2].metric("Customers to contact", f"{int(tg.customers.sum()):,}")
        c[3].metric(
            "Scenario: revenue protected",
            gbp(recovered),
            help="Assumption-driven. Set the lapse-rate cut in the sidebar.",
        )
        long = seg.melt(
            id_vars="segment",
            value_vars=["revenue_share", "lapse_rate"],
            var_name="measure",
            value_name="value",
        )
        long["measure"] = long.measure.map(
            {"revenue_share": "Share of revenue", "lapse_rate": "Lapse rate in winter"}
        )
        schart = (
            alt.Chart(long)
            .mark_bar()
            .encode(
                y=alt.Y(
                    "segment:N",
                    sort=list(seg.sort_values("revenue_at_risk", ascending=False).segment),
                    title=None,
                ),
                x=alt.X("value:Q", title="Percent", axis=alt.Axis(format="%")),
                yOffset="measure:N",
                color=alt.Color(
                    "measure:N",
                    title=None,
                    scale=alt.Scale(
                        domain=["Share of revenue", "Lapse rate in winter"], range=[BLUE, VERM]
                    ),
                    legend=alt.Legend(orient="bottom"),
                ),
                tooltip=["segment", "measure", alt.Tooltip("value:Q", format=".1%")],
            )
            .properties(
                title=chart_title(
                    f"{top.segment} hold {top.revenue_share * 100:.0f}% of revenue, and {top.lapse_rate * 100:.0f}% of them lapse in the winter quarter"
                ),
                height=360,
            )
        )
        st.altair_chart(schart, width="stretch")
        st.caption(
            "Lapse rate is measured: the share of each segment that did not buy in the following 3 months, in the same quarter a year earlier."
        )
        st.markdown(
            f"**Contact:** {', '.join(tg.segment) if len(tg) else 'no segment'}. These have above-average expected loss per customer. "
            f"With an assumed {reduction * 100:.0f}% lower lapse rate they would protect about **{gbp(recovered)}** of revenue next quarter "
            f"({gbp(recovered / tg.customers.sum()) if len(tg) else '£0'} per customer contacted). **This is a scenario based on your slider, not a measured result.**"
        )
        show_table(seg.rename(columns={"lapse_rate": "lapse_rate_winter"}))

# ---------------------------------------------------------------- Caveats
with tab4:
    st.subheader("What this data can and cannot tell us")
    st.markdown(
        "- **Not profit.** Revenue is quantity times price, net of returns. There are no costs, margins, discounts or campaign data, so the scenario in question 3 is a stated assumption, not a forecast.\n"
        "- **Returns** are cancellation invoices. They are subtracted on the date of the cancellation and cannot be linked to the original sale.\n"
        "- **Guest checkouts** have no customer ID. They are in revenue and orders, but not in customer counts, cohorts or segments.\n"
        "- **Cleaning:** an overlap between the two workbook sheets, exact duplicate lines, postage and fee lines, stock write-offs and zero-price lines are removed. Counts below.\n"
        "- **One winter.** Lapse rates for the December to February quarter come from a single year.\n"
        "- **Left-censored start.** Customers who bought before December 2009 appear as new in the first month, so that cohort is hidden.\n"
        "- **Wholesalers.** The dataset description says many customers are wholesalers; the biggest account is a few percent of all revenue.\n"
        "- **Licence.** UCI Online Retail II, CC BY 4.0. Independent portfolio project, not affiliated with the retailer."
    )
    try:
        dq = pd.read_csv(appdata.export_dir() / "dq_rule_log.csv")
        st.dataframe(
            dq[["rule_order", "rule", "kind", "n_rows", "share_of_raw_rows", "decision"]],
            hide_index=True,
        )
    except FileNotFoundError:
        st.caption("dq_rule_log.csv not found in exports/.")
