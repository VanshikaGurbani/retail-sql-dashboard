-- mart.orders: one row per invoice. Sale invoices carry positive value, cancellation invoices
-- negative value, so summing order_value over any slice gives net revenue for that slice.
CREATE OR REPLACE TABLE mart.orders AS
SELECT
    invoice_no,
    any_value(line_type)                          AS order_type,        -- 'sale' or 'return'
    min(invoice_ts)                               AS invoice_ts,
    CAST(min(invoice_ts) AS DATE)                 AS invoice_date,
    CAST(date_trunc('month', min(invoice_ts)) AS DATE) AS invoice_month,
    customer_id,                                                         -- NULL = guest checkout
    country,
    count(*)                                      AS n_lines,
    sum(quantity)                                 AS units,
    sum(line_value)                               AS order_value
FROM clean.lines
GROUP BY invoice_no, customer_id, country;

-- mart.daily_revenue: one row per calendar day in the analysis window, including days with no
-- trading (the shop records no sales on most Saturdays), so moving averages are not distorted
-- by missing dates.
CREATE OR REPLACE TABLE mart.daily_revenue AS
WITH spine AS (
    SELECT CAST(d AS DATE) AS date
    FROM generate_series(
        (SELECT window_start FROM dq.params),
        (SELECT window_end_excl - INTERVAL 1 DAY FROM dq.params),
        INTERVAL 1 DAY
    ) AS t(d)
),
daily AS (
    SELECT
        invoice_date AS date,
        sum(order_value) FILTER (WHERE order_type = 'sale')   AS sales_revenue,
        sum(order_value) FILTER (WHERE order_type = 'return') AS returns_value,
        sum(order_value)                                      AS net_revenue,
        count(*) FILTER (WHERE order_type = 'sale')           AS orders,
        sum(units) FILTER (WHERE order_type = 'sale')         AS units_sold,
        count(DISTINCT customer_id) FILTER (WHERE order_type = 'sale') AS active_customers
    FROM mart.orders
    GROUP BY invoice_date
),
filled AS (
    SELECT
        s.date,
        coalesce(d.sales_revenue, 0)  AS sales_revenue,
        coalesce(d.returns_value, 0)  AS returns_value,
        coalesce(d.net_revenue, 0)    AS net_revenue,
        coalesce(d.orders, 0)         AS orders,
        coalesce(d.units_sold, 0)     AS units_sold,
        coalesce(d.active_customers, 0) AS active_customers
    FROM spine AS s LEFT JOIN daily AS d USING (date)
)
SELECT
    *,
    orders > 0 AS is_trading_day,
    avg(net_revenue) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)  AS net_revenue_7d_avg,
    avg(net_revenue) OVER (ORDER BY date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) AS net_revenue_28d_avg,
    sum(net_revenue) OVER (ORDER BY date)                                           AS cumulative_net_revenue
FROM filled
ORDER BY date;
