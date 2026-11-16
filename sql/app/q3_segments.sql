-- Live RFM segments for the chosen countries, with lapse rates measured on the back-tests.
-- The date filter does not apply here: segments are a snapshot on 1 December 2011.
-- Parameters: $countries. Revenue at risk = quarterly run-rate x same-season lapse rate.
WITH base AS (
    SELECT segment, count(*) AS customers, sum(monetary) AS trailing_12m_net_revenue,
           sum(monetary) / 4.0 AS quarterly_run_rate
    FROM rfm
    WHERE list_contains($countries, country)
    GROUP BY segment
)
SELECT
    b.segment,
    b.customers,
    b.trailing_12m_net_revenue,
    b.trailing_12m_net_revenue / sum(b.trailing_12m_net_revenue) OVER () AS revenue_share,
    s.same_season_lapse_rate AS lapse_rate,
    b.quarterly_run_rate * s.same_season_lapse_rate AS revenue_at_risk,
    b.quarterly_run_rate * s.same_season_lapse_rate / b.customers AS at_risk_per_customer
FROM base AS b
JOIN rfm_summary AS s USING (segment)
ORDER BY revenue_at_risk DESC;
