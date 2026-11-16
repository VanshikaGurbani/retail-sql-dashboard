-- Scenario for the retention decision. Everything measured comes from mart.rfm_summary; the
-- ONLY invented inputs are the three rows of mart.scenario_assumptions below, and they are
-- labelled as assumptions everywhere they are shown. Output is revenue, not profit: the data
-- has no costs or margins.

-- Assumption: a retention campaign lowers the chance that a contacted customer goes quiet by
-- this share (for example 10% of a 60% lapse rate is 6 points, giving a 54% lapse rate).
CREATE OR REPLACE TABLE mart.scenario_assumptions AS
SELECT * FROM (VALUES
    ('low',  0.05),
    ('mid',  0.10),
    ('high', 0.20)
) AS t(case_name, lapse_reduction);

-- Which segments to contact: those whose expected loss per customer is above the average for
-- the whole identified base. Revenue at risk = quarterly run-rate (trailing 12 months / 4)
-- x same-season lapse rate, both measured.
CREATE OR REPLACE TABLE mart.segment_targeting AS
WITH s AS (
    SELECT
        segment, customers, revenue_share, same_season_lapse_rate,
        revenue_at_risk_next_quarter, revenue_at_risk_pooled_rates,
        customers * same_season_next_q_revenue_per_customer AS expected_next_q_revenue_do_nothing,
        revenue_at_risk_next_quarter / customers AS at_risk_per_customer
    FROM mart.rfm_summary
),
overall AS (
    SELECT sum(revenue_at_risk_next_quarter) / sum(customers) AS avg_at_risk_per_customer,
           sum(revenue_at_risk_next_quarter)                  AS total_at_risk
    FROM s
)
SELECT
    s.*,
    s.revenue_at_risk_next_quarter / o.total_at_risk AS share_of_total_at_risk,
    s.at_risk_per_customer > o.avg_at_risk_per_customer AS is_targeted
FROM s CROSS JOIN overall AS o
ORDER BY s.revenue_at_risk_next_quarter DESC;

-- Impact by case. recovered_revenue = revenue at risk in targeted segments x lapse reduction.
CREATE OR REPLACE TABLE mart.scenario AS
SELECT
    a.case_name,
    a.lapse_reduction,
    sum(t.customers) FILTER (WHERE t.is_targeted)                                AS customers_contacted,
    sum(t.revenue_at_risk_next_quarter)                                          AS total_revenue_at_risk,
    sum(t.revenue_at_risk_next_quarter) FILTER (WHERE t.is_targeted)             AS targeted_revenue_at_risk,
    sum(t.revenue_at_risk_next_quarter) FILTER (WHERE t.is_targeted) * a.lapse_reduction AS recovered_revenue,
    sum(t.revenue_at_risk_pooled_rates) FILTER (WHERE t.is_targeted) * a.lapse_reduction AS recovered_revenue_pooled_rates,
    sum(t.revenue_at_risk_next_quarter) FILTER (WHERE t.is_targeted) * a.lapse_reduction
        / sum(t.customers) FILTER (WHERE t.is_targeted)                          AS recovered_revenue_per_contact
FROM mart.scenario_assumptions AS a
CROSS JOIN mart.segment_targeting AS t
GROUP BY a.case_name, a.lapse_reduction
ORDER BY a.lapse_reduction;

-- Same impact split by segment, so the memo can show where the recovered revenue comes from.
CREATE OR REPLACE TABLE mart.scenario_segments AS
SELECT
    a.case_name,
    a.lapse_reduction,
    t.segment,
    t.customers,
    t.is_targeted,
    t.revenue_at_risk_next_quarter,
    t.revenue_at_risk_next_quarter * a.lapse_reduction              AS recovered_revenue,
    t.revenue_at_risk_next_quarter * a.lapse_reduction / t.customers AS recovered_revenue_per_contact
FROM mart.scenario_assumptions AS a
CROSS JOIN mart.segment_targeting AS t
ORDER BY a.lapse_reduction, t.revenue_at_risk_next_quarter DESC;

-- Context numbers the memo quotes: size of the base and where revenue and risk sit.
CREATE OR REPLACE TABLE mart.scenario_inputs AS
SELECT
    (SELECT count(*) FROM mart.rfm)                                          AS base_customers,
    (SELECT sum(monetary) FROM mart.rfm)                                     AS base_trailing_12m_net_revenue,
    (SELECT sum(monetary) / 4.0 FROM mart.rfm)                               AS base_quarterly_run_rate,
    (SELECT sum(revenue_at_risk_next_quarter) FROM mart.segment_targeting)   AS total_revenue_at_risk,
    (SELECT sum(revenue_at_risk_next_quarter) FROM mart.segment_targeting)
        / (SELECT sum(monetary) / 4.0 FROM mart.rfm)                         AS at_risk_share_of_run_rate,
    (SELECT sum(customers) FROM mart.segment_targeting WHERE is_targeted)    AS targeted_customers,
    (SELECT sum(customers) FROM mart.segment_targeting WHERE is_targeted)
        * 1.0 / (SELECT count(*) FROM mart.rfm)                              AS targeted_customer_share,
    (SELECT sum(revenue_share) FROM mart.segment_targeting WHERE is_targeted) AS targeted_revenue_share,
    (SELECT sum(revenue_at_risk_next_quarter) FROM mart.segment_targeting WHERE is_targeted) AS targeted_revenue_at_risk,
    (SELECT sum(revenue_at_risk_next_quarter) FROM mart.segment_targeting WHERE is_targeted)
        / (SELECT sum(revenue_at_risk_next_quarter) FROM mart.segment_targeting) AS targeted_share_of_at_risk,
    (SELECT sum(customers * same_season_lapse_rate) FILTER (WHERE is_targeted)
            / sum(customers) FILTER (WHERE is_targeted) FROM mart.segment_targeting) AS targeted_lapse_rate,
    (SELECT sum(expected_next_q_revenue_do_nothing) FROM mart.segment_targeting) AS expected_next_q_revenue_do_nothing,
    (SELECT sum(customers * same_season_lapse_rate) / sum(customers)
       FROM mart.segment_targeting)                                          AS base_weighted_lapse_rate;
