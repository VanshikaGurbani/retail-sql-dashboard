-- mart.customer_months: one row per identified customer and month in which they bought.
-- "Active in a month" means at least one sale invoice; a return alone does not count.
CREATE OR REPLACE TABLE mart.customer_months AS
SELECT
    customer_id,
    invoice_month AS month,
    count(*) FILTER (WHERE order_type = 'sale') AS sale_orders,
    sum(order_value)                            AS net_revenue
FROM mart.orders
WHERE customer_id IS NOT NULL
GROUP BY customer_id, invoice_month
HAVING count(*) FILTER (WHERE order_type = 'sale') > 0;

-- mart.customers: lifetime table, one row per identified customer with at least one sale.
CREATE OR REPLACE TABLE mart.customers AS
WITH sale_orders AS (
    SELECT
        customer_id, invoice_no, invoice_date, order_value,
        lag(invoice_date) OVER (PARTITION BY customer_id ORDER BY invoice_ts, invoice_no) AS prev_order_date
    FROM mart.orders
    WHERE customer_id IS NOT NULL AND order_type = 'sale'
),
agg AS (
    SELECT
        customer_id,
        min(invoice_date)                                 AS first_order_date,
        max(invoice_date)                                 AS last_order_date,
        count(*)                                          AS n_orders,
        sum(order_value)                                  AS sales_value,
        avg(date_diff('day', prev_order_date, invoice_date)) AS avg_days_between_orders
    FROM sale_orders
    GROUP BY customer_id
),
returns AS (
    SELECT customer_id, sum(order_value) AS returns_value
    FROM mart.orders
    WHERE customer_id IS NOT NULL AND order_type = 'return'
    GROUP BY customer_id
),
units AS (
    SELECT customer_id, sum(units) FILTER (WHERE order_type = 'sale') AS units_bought,
           count(DISTINCT invoice_month) FILTER (WHERE order_type = 'sale') AS active_months
    FROM mart.orders
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
),
joined AS (
    SELECT
        a.customer_id,
        h.home_country,
        CAST(date_trunc('month', a.first_order_date) AS DATE) AS cohort_month,
        a.first_order_date,
        a.last_order_date,
        date_diff('day', a.first_order_date, a.last_order_date) AS tenure_days,
        a.n_orders,
        u.active_months,
        u.units_bought,
        a.sales_value,
        coalesce(r.returns_value, 0)                    AS returns_value,
        a.sales_value + coalesce(r.returns_value, 0)    AS net_revenue,
        a.sales_value / a.n_orders                      AS avg_order_value,
        a.avg_days_between_orders
    FROM agg AS a
    JOIN units AS u USING (customer_id)
    LEFT JOIN returns AS r USING (customer_id)
    LEFT JOIN clean.customer_home_country AS h USING (customer_id)
)
SELECT
    *,
    row_number() OVER (ORDER BY net_revenue DESC, customer_id)               AS revenue_rank,
    sum(net_revenue) OVER (ORDER BY net_revenue DESC, customer_id)
        / sum(net_revenue) OVER ()                                           AS cumulative_revenue_share,
    ntile(10) OVER (ORDER BY net_revenue DESC, customer_id)                  AS revenue_decile
FROM joined;
