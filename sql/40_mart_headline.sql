-- Headline KPIs and small chart tables. Every number in README, RESULTS.md and MEMO.md that
-- is not a threshold or an assumption is read from here or from the other mart tables.

-- mart.revenue_bridge: from every raw row to the rows the KPIs use. rows and revenue are
-- signed so the steps add up: raw = kept + excluded. 'revenue' is quantity x price.
CREATE OR REPLACE TABLE mart.revenue_bridge AS
SELECT 0 AS step, 'raw file' AS label, count(*) AS n_rows,
       sum(line_value) AS revenue
FROM stg.transactions
UNION ALL
SELECT rule_order, rule, -n_rows, -coalesce(revenue, 0)
FROM dq.rule_log
WHERE kind = 'excluded'
UNION ALL
SELECT 99, 'kept (clean.lines)', count(*), sum(line_value)
FROM clean.lines
ORDER BY step;

-- mart.retention_curve: share of a cohort still buying k months after their first purchase.
-- The first cohort (December 2009) is excluded: it contains customers who were already
-- buying before the file starts, so it would overstate retention.
CREATE OR REPLACE TABLE mart.retention_curve AS
SELECT
    month_offset,
    count(DISTINCT cohort_month)                    AS cohorts_observed,
    sum(cohort_size)                                AS customers,
    sum(active_customers)                           AS active_customers,
    sum(active_customers) * 1.0 / sum(cohort_size)  AS retention_rate
FROM mart.cohorts
WHERE NOT is_first_window_cohort
GROUP BY month_offset
ORDER BY month_offset;

-- mart.headline: one row.
CREATE OR REPLACE TABLE mart.headline AS
WITH o AS (
    SELECT * FROM mart.orders
),
yr AS (
    SELECT
        sum(order_value)                                                  AS net_revenue,
        sum(order_value) FILTER (WHERE invoice_date <  DATE '2010-12-01') AS net_revenue_year1,
        sum(order_value) FILTER (WHERE invoice_date >= DATE '2010-12-01') AS net_revenue_year2,
        sum(order_value) FILTER (WHERE order_type = 'sale')               AS sales_revenue,
        sum(order_value) FILTER (WHERE order_type = 'return')             AS returns_value,
        sum(order_value) FILTER (WHERE customer_id IS NULL)               AS net_revenue_guest,
        count(*) FILTER (WHERE order_type = 'sale')                       AS orders,
        sum(units) FILTER (WHERE order_type = 'sale')                     AS units_sold,
        median(order_value) FILTER (WHERE order_type = 'sale')            AS median_order_value,
        avg(order_value) FILTER (WHERE order_type = 'sale')               AS mean_order_value
    FROM o
),
ident AS (
    SELECT
        count(*)                                                 AS customers,
        sum(CAST(n_orders = 1 AS INTEGER)) * 1.0 / count(*)      AS one_order_share,
        sum(CAST(n_orders >= 2 AS INTEGER)) * 1.0 / count(*)     AS repeat_share,
        sum(net_revenue) FILTER (WHERE revenue_decile = 1) / sum(net_revenue) AS top_decile_revenue_share,
        max(cumulative_revenue_share) FILTER (WHERE revenue_rank = 1)         AS top1_customer_share,
        median(n_orders)                                         AS median_orders_per_customer,
        median(avg_days_between_orders)                          AS median_days_between_orders
    FROM mart.customers
),
season AS (
    SELECT
        sum(net_revenue) FILTER (WHERE month BETWEEN DATE '2010-09-01' AND DATE '2010-11-01')
            / sum(net_revenue) FILTER (WHERE month <= DATE '2010-11-01') AS sepnov_share_year1,
        sum(net_revenue) FILTER (WHERE month BETWEEN DATE '2011-09-01' AND DATE '2011-11-01')
            / sum(net_revenue) FILTER (WHERE month >= DATE '2010-12-01') AS sepnov_share_year2
    FROM mart.monthly
),
ctry AS (
    SELECT
        max(country) FILTER (WHERE revenue_rank = 1)        AS top_country,
        max(revenue_share) FILTER (WHERE revenue_rank = 1)  AS top_country_share,
        count(*)                                            AS countries
    FROM mart.countries
),
prod AS (
    SELECT
        count(*)                                                   AS products,
        max(cumulative_revenue_share) FILTER (WHERE revenue_rank = 20) AS top20_products_share
    FROM mart.products
)
SELECT
    (SELECT window_start FROM dq.params)                      AS window_start,
    (SELECT window_end_excl - INTERVAL 1 DAY FROM dq.params) AS window_end,
    (SELECT count(*) FROM raw.online_retail)                  AS raw_rows,
    (SELECT count(*) FROM clean.lines)                        AS kept_rows,
    (SELECT sum(line_value) FROM stg.transactions)            AS raw_revenue,
    yr.*,
    -yr.returns_value / yr.sales_revenue                      AS return_rate,
    yr.net_revenue_year2 / yr.net_revenue_year1 - 1           AS yoy_growth,
    yr.net_revenue_guest / yr.net_revenue                     AS guest_revenue_share,
    ident.*,
    season.*,
    ctry.*,
    prod.*,
    (SELECT revenue_effect FROM mart.yoy_decomposition WHERE sort_order = 4) AS identified_revenue_change,
    (SELECT year1_value FROM mart.yoy_decomposition WHERE sort_order = 4)    AS identified_revenue_year1,
    (SELECT year2_value FROM mart.yoy_decomposition WHERE sort_order = 4)    AS identified_revenue_year2
FROM yr, ident, season, ctry, prod;
