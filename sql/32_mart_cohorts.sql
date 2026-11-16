-- mart.cohorts: monthly acquisition cohorts. A customer belongs to the month of their first
-- sale. month_offset 0 is that month, 1 the next, and so on. Grain is cohort x offset x country
-- (customer home country), which makes every count additive across countries so the dashboard
-- can filter by country and still compute retention as active / cohort size.
-- Only complete months are used, so a cohort has no row for offsets beyond November 2011.
CREATE OR REPLACE TABLE mart.cohorts AS
WITH bounds AS (
    SELECT CAST(date_trunc('month', window_start) AS DATE) AS first_month,
           CAST(date_trunc('month', window_end_excl - INTERVAL 1 DAY) AS DATE) AS last_month
    FROM dq.params
),
cohort_customers AS (
    SELECT customer_id, cohort_month, home_country AS country
    FROM mart.customers
),
grid AS (
    SELECT c.cohort_month, c.country, o.month_offset, count(*) AS cohort_size
    FROM cohort_customers AS c
    CROSS JOIN bounds AS b
    CROSS JOIN LATERAL (
        SELECT unnest(range(0, date_diff('month', c.cohort_month, b.last_month) + 1)) AS month_offset
    ) AS o
    GROUP BY c.cohort_month, c.country, o.month_offset
),
activity AS (
    SELECT
        c.cohort_month,
        c.country,
        date_diff('month', c.cohort_month, m.month) AS month_offset,
        count(DISTINCT m.customer_id) AS active_customers,
        sum(m.net_revenue)            AS net_revenue
    FROM mart.customer_months AS m
    JOIN cohort_customers AS c USING (customer_id)
    GROUP BY 1, 2, 3
)
SELECT
    g.cohort_month,
    g.country,
    g.month_offset,
    g.cohort_size,
    coalesce(a.active_customers, 0)  AS active_customers,
    coalesce(a.net_revenue, 0)       AS net_revenue,
    coalesce(a.active_customers, 0) * 1.0 / g.cohort_size AS retention_rate,
    g.cohort_month = (SELECT first_month FROM bounds) AS is_first_window_cohort
FROM grid AS g
LEFT JOIN activity AS a USING (cohort_month, country, month_offset)
ORDER BY g.cohort_month, g.country, g.month_offset;
