-- mart.product_months: stock code x month x country. Small enough to ship with the app, and
-- additive, so the dashboard can filter by date range and country and re-rank products.
CREATE OR REPLACE TABLE mart.product_months AS
WITH names AS (
    -- one display name per stock code: its most common description
    SELECT stock_code, description
    FROM (
        SELECT stock_code, description, count(*) AS n,
               row_number() OVER (PARTITION BY stock_code ORDER BY count(*) DESC, description) AS rn
        FROM clean.lines
        WHERE description IS NOT NULL
        GROUP BY stock_code, description
    )
    WHERE rn = 1
)
SELECT
    l.invoice_month AS month,
    l.country,
    l.stock_code,
    coalesce(n.description, l.stock_code) AS description,
    sum(l.line_value) FILTER (WHERE l.line_type = 'sale')   AS sales_revenue,
    sum(l.line_value) FILTER (WHERE l.line_type = 'return') AS returns_value,
    sum(l.line_value)                                       AS net_revenue,
    sum(l.quantity) FILTER (WHERE l.line_type = 'sale')     AS units_sold,
    count(DISTINCT l.invoice_no) FILTER (WHERE l.line_type = 'sale') AS orders_with_product
FROM clean.lines AS l
LEFT JOIN names AS n USING (stock_code)
GROUP BY l.invoice_month, l.country, l.stock_code, coalesce(n.description, l.stock_code);

-- mart.products: all-time product ranking with a Pareto share.
CREATE OR REPLACE TABLE mart.products AS
WITH p AS (
    SELECT
        stock_code,
        any_value(description)        AS description,
        sum(net_revenue)              AS net_revenue,
        sum(sales_revenue)            AS sales_revenue,
        sum(returns_value)            AS returns_value,
        sum(units_sold)               AS units_sold,
        sum(orders_with_product)      AS orders_with_product
    FROM mart.product_months
    GROUP BY stock_code
)
SELECT
    *,
    -returns_value / nullif(sales_revenue, 0)                                   AS return_rate,
    row_number() OVER (ORDER BY net_revenue DESC, stock_code)                   AS revenue_rank,
    sum(net_revenue) OVER (ORDER BY net_revenue DESC, stock_code ROWS UNBOUNDED PRECEDING)
        / sum(net_revenue) OVER ()                                              AS cumulative_revenue_share
FROM p;

-- mart.countries: country ranking, year over year.
CREATE OR REPLACE TABLE mart.countries AS
WITH c AS (
    SELECT
        country,
        sum(order_value)                                                     AS net_revenue,
        sum(order_value) FILTER (WHERE invoice_date < DATE '2010-12-01')     AS net_revenue_year1,
        sum(order_value) FILTER (WHERE invoice_date >= DATE '2010-12-01')    AS net_revenue_year2,
        count(*) FILTER (WHERE order_type = 'sale')                          AS orders,
        count(DISTINCT customer_id) FILTER (WHERE order_type = 'sale')       AS customers,
        sum(order_value) FILTER (WHERE order_type = 'sale')
            / nullif(count(*) FILTER (WHERE order_type = 'sale'), 0)         AS avg_order_value
    FROM mart.orders
    GROUP BY country
)
SELECT
    *,
    net_revenue / sum(net_revenue) OVER ()            AS revenue_share,
    net_revenue_year2 / nullif(net_revenue_year1, 0) - 1 AS yoy_growth,
    row_number() OVER (ORDER BY net_revenue DESC, country) AS revenue_rank
FROM c;

-- mart.product_months_app: the same grain, capped for the dashboard and for exports. Products
-- outside the top 500 by net revenue are rolled into one 'OTHER' stock code per month and
-- country, so totals still reconcile while the file stays small enough to ship with the app.
CREATE OR REPLACE TABLE mart.product_months_app AS
WITH ranked AS (
    SELECT pm.*, p.revenue_rank
    FROM mart.product_months AS pm
    JOIN mart.products AS p USING (stock_code)
)
SELECT
    month, country,
    CASE WHEN revenue_rank <= 500 THEN stock_code ELSE 'OTHER' END AS stock_code,
    CASE WHEN revenue_rank <= 500 THEN any_value(description) ELSE 'All other products' END AS description,
    sum(sales_revenue)  AS sales_revenue,
    sum(returns_value)  AS returns_value,
    sum(net_revenue)    AS net_revenue,
    sum(units_sold)     AS units_sold,
    sum(orders_with_product) AS orders_with_product
FROM ranked
GROUP BY month, country, CASE WHEN revenue_rank <= 500 THEN stock_code ELSE 'OTHER' END, revenue_rank <= 500;
