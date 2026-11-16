-- mart.monthly: the revenue-driver table behind question 1. One row per complete month.
-- Identified-customer revenue splits exactly into
--     net revenue = active customers x orders per customer x net revenue per order
-- so a change in revenue can be assigned to customers, frequency or basket size.
-- (Guest checkouts have no customer ID, so they are shown separately, not decomposed.)
CREATE OR REPLACE TABLE mart.monthly AS
WITH months AS (
    SELECT CAST(d AS DATE) AS month
    FROM generate_series(
        (SELECT CAST(date_trunc('month', window_start) AS DATE) FROM dq.params),
        (SELECT CAST(date_trunc('month', window_end_excl - INTERVAL 1 DAY) AS DATE) FROM dq.params),
        INTERVAL 1 MONTH
    ) AS t(d)
),
base AS (
    SELECT
        invoice_month AS month,
        sum(order_value) FILTER (WHERE order_type = 'sale')                     AS sales_revenue,
        sum(order_value) FILTER (WHERE order_type = 'return')                   AS returns_value,
        sum(order_value)                                                        AS net_revenue,
        sum(order_value) FILTER (WHERE customer_id IS NOT NULL)                 AS net_revenue_identified,
        sum(order_value) FILTER (WHERE customer_id IS NULL)                     AS net_revenue_guest,
        count(*) FILTER (WHERE order_type = 'sale')                             AS orders,
        count(*) FILTER (WHERE order_type = 'sale' AND customer_id IS NOT NULL) AS orders_identified,
        sum(units) FILTER (WHERE order_type = 'sale')                           AS units_sold,
        count(DISTINCT customer_id) FILTER (WHERE order_type = 'sale')          AS active_customers
    FROM mart.orders
    GROUP BY invoice_month
),
new_customers AS (
    SELECT cohort_month AS month, count(*) AS new_customers
    FROM mart.customers
    GROUP BY cohort_month
),
joined AS (
    SELECT
        m.month,
        coalesce(b.sales_revenue, 0)          AS sales_revenue,
        coalesce(b.returns_value, 0)          AS returns_value,
        coalesce(b.net_revenue, 0)            AS net_revenue,
        coalesce(b.net_revenue_identified, 0) AS net_revenue_identified,
        coalesce(b.net_revenue_guest, 0)      AS net_revenue_guest,
        coalesce(b.orders, 0)                 AS orders,
        coalesce(b.orders_identified, 0)      AS orders_identified,
        coalesce(b.units_sold, 0)             AS units_sold,
        coalesce(b.active_customers, 0)       AS active_customers,
        coalesce(n.new_customers, 0)          AS new_customers
    FROM months AS m
    LEFT JOIN base AS b USING (month)
    LEFT JOIN new_customers AS n USING (month)
)
SELECT
    month,
    sales_revenue, returns_value, net_revenue, net_revenue_identified, net_revenue_guest,
    orders, orders_identified, units_sold,
    active_customers, new_customers,
    active_customers - new_customers                                   AS returning_customers,
    orders_identified * 1.0 / nullif(active_customers, 0)              AS orders_per_customer,
    net_revenue_identified / nullif(orders_identified, 0)              AS net_revenue_per_order,
    -returns_value / nullif(sales_revenue, 0)                          AS return_rate,
    net_revenue_guest / nullif(net_revenue, 0)                         AS guest_revenue_share,
    net_revenue / lag(net_revenue, 1)  OVER (ORDER BY month) - 1       AS mom_growth,
    net_revenue / lag(net_revenue, 12) OVER (ORDER BY month) - 1       AS yoy_growth,
    avg(net_revenue) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS net_revenue_3m_avg,
    net_revenue / avg(net_revenue) OVER ()                             AS seasonality_index
FROM joined
ORDER BY month;

-- mart.yoy_decomposition: year 1 (December 2009 to November 2010) against year 2 (December 2010
-- to November 2011), identified customers only. Uses the log-mean (LMDI) split, so the three
-- effects add up exactly to the change in revenue with no residual.
CREATE OR REPLACE TABLE mart.yoy_decomposition AS
WITH yearly AS (
    SELECT
        CASE WHEN o.invoice_date < DATE '2010-12-01' THEN 1 ELSE 2 END AS yr,
        count(DISTINCT o.customer_id) FILTER (WHERE o.order_type = 'sale')        AS customers,
        count(*) FILTER (WHERE o.order_type = 'sale')                             AS orders,
        sum(o.order_value)                                                        AS revenue
    FROM mart.orders AS o
    WHERE o.customer_id IS NOT NULL
    GROUP BY 1
),
metrics AS (
    SELECT yr, customers, orders, revenue,
           orders * 1.0 / customers AS orders_per_customer,
           revenue / orders         AS revenue_per_order
    FROM yearly
),
pair AS (
    SELECT
        y1.customers AS c0, y2.customers AS c1,
        y1.orders_per_customer AS f0, y2.orders_per_customer AS f1,
        y1.revenue_per_order AS a0, y2.revenue_per_order AS a1,
        y1.revenue AS r0, y2.revenue AS r1,
        (y2.revenue - y1.revenue) / ln(y2.revenue / y1.revenue) AS log_mean
    FROM metrics AS y1, metrics AS y2
    WHERE y1.yr = 1 AND y2.yr = 2
)
SELECT * FROM (
    SELECT 1 AS sort_order, 'Active customers' AS driver, c0 AS year1_value, c1 AS year2_value,
           log_mean * ln(c1 * 1.0 / c0) AS revenue_effect FROM pair
    UNION ALL
    SELECT 2, 'Orders per customer', f0, f1, log_mean * ln(f1 / f0) FROM pair
    UNION ALL
    SELECT 3, 'Net revenue per order', a0, a1, log_mean * ln(a1 / a0) FROM pair
    UNION ALL
    SELECT 4, 'Total change in identified net revenue', r0, r1, r1 - r0 FROM pair
) ORDER BY sort_order;
