# Exports

Flat CSV files (UTF-8, header row) written by `retail export` from the DuckDB mart tables, for rebuilding the dashboard
in Tableau Public or Power BI. Revenue is net of returns and is not profit. Money is rounded to 2 decimals and rates to 4.
Definitions: [docs/KPI_DEFINITIONS.md](../docs/KPI_DEFINITIONS.md). Source data: UCI Online Retail II, CC BY 4.0.

| File | Rows | Contents |
|---|---:|---|
| `mart_monthly.csv` | 24 | One row per month: revenue, returns, orders, active and new customers, orders per customer, revenue per order, growth, seasonality index. |
| `mart_yoy_decomposition.csv` | 4 | Year-on-year change in identified-customer revenue split into customers, orders per customer and revenue per order. |
| `mart_daily_revenue.csv` | 730 | One row per calendar day with 7 and 28 day averages and cumulative revenue. |
| `mart_orders.csv` | 45,969 | One row per invoice (sale or return) with date, month, customer, country, units and value. The base table for any date and country filter. |
| `mart_customers.csv` | 5,824 | One row per identified customer: first and last order, orders, revenue, order value, revenue rank and decile. |
| `mart_cohorts.csv` | 4,103 | Cohort by month offset by country: cohort size, active customers, retention rate, revenue. |
| `mart_rfm.csv` | 4,293 | Live RFM segmentation (1 December 2011) for each identified customer. |
| `mart_rfm_backtest.csv` | 20,446 | RFM segmentation at five past snapshots with what each customer did in the next 3 months. |
| `mart_rfm_summary.csv` | 6 | One row per segment: customers, revenue share, measured lapse rates and revenue at risk. |
| `mart_segment_targeting.csv` | 6 | Revenue at risk per customer by segment and whether the segment is targeted. |
| `mart_scenario_assumptions.csv` | 3 | The three assumed lapse reductions. These are assumptions, not measurements. |
| `mart_scenario.csv` | 3 | Revenue protected under each assumption. A scenario, not a result. |
| `mart_scenario_segments.csv` | 18 | The same scenario split by segment. |
| `mart_scenario_inputs.csv` | 1 | Size of the base, revenue at risk and the other inputs the memo quotes. |
| `mart_products.csv` | 4,738 | All-time product ranking with return rate and cumulative revenue share. |
| `mart_product_months_app.csv` | 36,603 | Product by month by country (top 500 products, the rest grouped as OTHER). |
| `mart_countries.csv` | 43 | Country ranking with year-on-year growth. |
| `dq_rule_log.csv` | 14 | Every data-quality rule with rows and revenue affected and the decision taken. |
