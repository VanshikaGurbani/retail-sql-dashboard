# KPI definitions

Every KPI is defined once here and computed once in SQL (the file is named for each). "Kept lines" are the rows
that survive the cleaning rules in [DATA_QUALITY.md](DATA_QUALITY.md). All money is pounds sterling, quantity
times unit price. The data has no costs or margins, so **no KPI here is profit**.

## Scope

| Term | Definition | Where |
|---|---|---|
| Analysis window | 1 December 2009 to 30 November 2011, 24 complete months. December 2011 stops on the 9th and is left out so a partial month cannot look like a sales collapse. | `dq.params` in `sql/00_schemas.sql` |
| Year 1, year 2 | December 2009 to November 2010, and December 2010 to November 2011. | `sql/33_mart_monthly.sql` |
| Sale line | Kept line with positive quantity on a normal invoice. | `sql/21_clean_lines.sql` |
| Return line | Kept line with negative quantity on a cancellation invoice (invoice number starts with C). | `sql/21_clean_lines.sql` |
| Merchandise | Product sales only. Postage, carriage, fees, manual and discount lines, bad-debt entries, gift vouchers and test products are excluded. | `sql/20_dq_flags.sql` |
| Order | One invoice. `mart.orders` has one row per invoice. | `sql/30_mart_orders_daily.sql` |
| Identified customer | A customer with a customer ID. Guest checkouts have none. | `sql/21_clean_lines.sql` |
| Customer country | The country on the customer's first sale. Guest invoices keep their own country. | `sql/21_clean_lines.sql` |

## Revenue KPIs (all orders, guests included)

| KPI | Definition |
|---|---|
| Sales revenue | Sum of line value on sale lines. |
| Returns value | Sum of line value on return lines (a negative number), dated on the cancellation invoice. |
| **Net revenue** | Sales revenue plus returns value. This is the headline revenue. It is net of returns, excludes non-merchandise lines and is not profit. |
| Return rate | Returns value (made positive) divided by sales revenue, in the same period. Returns cannot be linked to the original sale, so a month's return rate can include sales from earlier months. |
| Orders | Count of sale invoices. Cancellation invoices are not orders. |
| Net revenue per order | Net revenue of identified customers divided by their sale invoices. Used in the revenue decomposition. |
| Mean and median order value | Mean and median invoice value over sale invoices. The median is quoted next to the mean because a few very large orders lift the mean. |
| Guest revenue share | Net revenue with no customer ID divided by total net revenue. |
| 3-month average | Average of the month and the two before it. |
| Seasonality index | A month's net revenue divided by the average month. |
| Year-on-year change | Year 2 net revenue divided by year 1, minus 1. In `mart.monthly`, the same month 12 months earlier. |

## Customer KPIs (identified customers only)

| KPI | Definition |
|---|---|
| **Active customer** | A customer with at least one sale invoice in the period (month or date range). A return alone does not make a customer active. |
| New customer | A customer whose first sale invoice falls in the month. |
| Returning customer | Active in the month but not new. |
| Orders per customer | Sale invoices of identified customers divided by active identified customers in the same period. |
| Revenue decomposition | Net revenue of identified customers equals active customers times orders per customer times net revenue per order. Year-on-year change is split into these three effects with the log-mean (LMDI) method, so they sum to the total change with no residual (`mart.yoy_decomposition`). |
| Customer lifetime table | One row per identified customer with a sale: first and last order date, number of orders, net revenue, average order value, average days between orders, revenue rank and cumulative revenue share (`mart.customers`). |
| Revenue concentration | Share of identified-customer net revenue held by the top 10% of customers (by net revenue) and by the single largest customer. |
| Bought once | Customers with exactly one sale invoice over the whole window. |

## Cohort retention

| Term | Definition |
|---|---|
| Cohort | The month of a customer's first sale invoice. |
| Month offset | Months since the cohort month. Offset 0 is the cohort month. |
| Retention rate | Customers from the cohort with at least one sale invoice in the offset month, divided by the cohort size. Offset 0 is 100% by construction. |
| Observable cells | Only complete months in the window, so a cohort has no cell beyond November 2011. |
| First cohort | The December 2009 cohort contains customers who were already buying before the file starts, so it overstates retention. It is excluded from the retention curve and hidden in the dashboard. |
| Retention curve | Customers active at the offset summed over cohorts, divided by customers in those same cohorts (`mart.retention_curve`). |

Grain of `mart.cohorts` is cohort, customer country and offset, so counts add up across countries and the
dashboard can filter by country.

## RFM segments (`sql/35_mart_rfm.sql`)

Computed at a snapshot date, from the 365 days before it, for identified customers with at least one sale in
that window.

| Measure | Definition |
|---|---|
| Recency | Days from the customer's last sale before the snapshot to the snapshot date. |
| Frequency | Sale invoices in the window. |
| Monetary | Net revenue (sales minus returns) in the window. |
| Scores | Each measure is scored 1 to 5 by percentile rank within the snapshot (5 is best; for recency, fewer days is better). Tied customers share a score. |

| Segment | Rule |
|---|---|
| Champions | Recency score 4 or 5 and frequency score 4 or 5 |
| Loyal | Recency 3 or better and frequency 3 or better, not Champions |
| Recent, low frequency | Recency 4 or 5 and frequency 1 or 2 |
| Cooling | Recency 3 and frequency 1 or 2 |
| At risk, high frequency | Recency 1 or 2 and frequency 3 or better |
| Dormant | Recency 1 or 2 and frequency 1 or 2 |

Snapshots are listed in `dq.snapshots`. The live segmentation is 1 December 2011. The back-tests are
1 September 2010, 1 December 2010, 1 March 2011, 1 June 2011 and 1 September 2011, each followed by a fully
observed quarter.

## Churn, risk and the scenario (`sql/35_`, `sql/36_`)

| KPI | Definition |
|---|---|
| Lapse (churn) | A customer in a back-test snapshot who made no purchase in the 3 months after it. Customers are never marked churned by an arbitrary inactivity rule; the lapse is what actually happened. |
| Lapse rate | Lapsed customers in a segment divided by the segment's customers at the back-test snapshot. |
| Base-case lapse rate | The lapse rate at the 1 December 2010 snapshot, the same season (December to February) as the quarter being planned. The other four back-tests give the range. |
| Quarterly run-rate | A segment's net revenue in the 365 days before the snapshot, divided by 4. |
| **Revenue at risk** | Quarterly run-rate times base-case lapse rate. The expected quarterly value of customers who go quiet. |
| Targeted segments | Segments whose revenue at risk per customer is above the average for the whole identified base (`mart.segment_targeting`). |
| Expected revenue if nothing is done | Customers in each segment times the average net revenue per customer that segment produced in the same quarter a year earlier. |
| **Scenario (assumption)** | Revenue protected = revenue at risk in the targeted segments times an assumed reduction in their lapse rate. The reductions (5%, 10%, 20%) are assumptions written in `mart.scenario_assumptions`; nothing in the data measures a campaign. The low end of the memo's range re-runs the calculation with all-season average lapse rates instead of the winter ones. |

The scenario is revenue, not profit. Comparing it with the cost of a contact requires a margin and a unit cost
that the data does not contain.
