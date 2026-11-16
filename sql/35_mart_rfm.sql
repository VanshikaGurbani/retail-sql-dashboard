-- RFM segmentation at every snapshot in dq.snapshots.
--   Recency   = days from the customer's last sale before the snapshot to the snapshot date
--   Frequency = sale invoices in the 365 days before the snapshot
--   Monetary  = net revenue (sales minus returns) in the same 365 days
-- Each is scored 1 to 5 within the snapshot by percentile rank (5 is best). Ties share a score,
-- so a customer base where many people bought once is not split arbitrarily.
-- For back-test snapshots the next 3 months are fully observed, so each customer also carries
-- what actually happened: did they buy again, and what did they spend.
CREATE OR REPLACE TABLE mart.rfm_snapshots AS
WITH snaps AS (
    SELECT snapshot_date, kind,
           CAST(snapshot_date + (SELECT outcome_months FROM dq.params) * INTERVAL 1 MONTH AS DATE) AS outcome_end
    FROM dq.snapshots
),
history AS (
    SELECT
        s.snapshot_date, s.kind, s.outcome_end,
        o.customer_id,
        date_diff('day', max(o.invoice_date) FILTER (WHERE o.order_type = 'sale'), s.snapshot_date) AS recency_days,
        count(*) FILTER (WHERE o.order_type = 'sale') AS frequency,
        sum(o.order_value)                            AS monetary
    FROM snaps AS s
    JOIN mart.orders AS o
      ON o.customer_id IS NOT NULL
     AND o.invoice_date <  s.snapshot_date
     AND o.invoice_date >= s.snapshot_date - (SELECT rfm_window_days FROM dq.params) * INTERVAL 1 DAY
    GROUP BY s.snapshot_date, s.kind, s.outcome_end, o.customer_id
    HAVING count(*) FILTER (WHERE o.order_type = 'sale') > 0
),
scored AS (
    SELECT
        *,
        least(5, 1 + CAST(floor(5 * percent_rank() OVER (PARTITION BY snapshot_date ORDER BY recency_days DESC)) AS INTEGER)) AS r_score,
        least(5, 1 + CAST(floor(5 * percent_rank() OVER (PARTITION BY snapshot_date ORDER BY frequency))          AS INTEGER)) AS f_score,
        least(5, 1 + CAST(floor(5 * percent_rank() OVER (PARTITION BY snapshot_date ORDER BY monetary))           AS INTEGER)) AS m_score
    FROM history
),
segmented AS (
    SELECT
        *,
        CASE
            WHEN r_score >= 4 AND f_score >= 4 THEN 'Champions'
            WHEN r_score >= 3 AND f_score >= 3 THEN 'Loyal'
            WHEN r_score >= 4 AND f_score <= 2 THEN 'Recent, low frequency'
            WHEN r_score  = 3 AND f_score <= 2 THEN 'Cooling'
            WHEN r_score <= 2 AND f_score >= 3 THEN 'At risk, high frequency'
            ELSE 'Dormant'
        END AS segment
    FROM scored
),
outcomes AS (
    SELECT
        s.snapshot_date, s.customer_id,
        count(*) FILTER (WHERE o.order_type = 'sale') AS next_orders,
        coalesce(sum(o.order_value), 0)               AS next_net_revenue
    FROM snaps AS sn
    JOIN segmented AS s USING (snapshot_date)
    LEFT JOIN mart.orders AS o
      ON o.customer_id = s.customer_id
     AND o.invoice_date >= s.snapshot_date
     AND o.invoice_date <  sn.outcome_end
    GROUP BY s.snapshot_date, s.customer_id
)
SELECT
    g.snapshot_date, g.kind, g.customer_id, h.home_country AS country,
    g.recency_days, g.frequency, g.monetary,
    g.r_score, g.f_score, g.m_score, g.segment,
    -- Outcomes exist only for back-tests (kind = 'backtest'); NULL for the live snapshot.
    CASE WHEN g.kind = 'backtest' THEN o.next_orders > 0 END                    AS bought_next_quarter,
    CASE WHEN g.kind = 'backtest' THEN o.next_net_revenue END                   AS next_quarter_net_revenue
FROM segmented AS g
LEFT JOIN outcomes AS o USING (snapshot_date, customer_id)
LEFT JOIN clean.customer_home_country AS h USING (customer_id);

-- mart.rfm: the live segmentation the recommendation acts on.
CREATE OR REPLACE TABLE mart.rfm AS
SELECT snapshot_date, customer_id, country, recency_days, frequency, monetary,
       r_score, f_score, m_score, segment
FROM mart.rfm_snapshots
WHERE kind = 'current';

-- mart.rfm_backtest: the measured history used for lapse rates.
CREATE OR REPLACE TABLE mart.rfm_backtest AS
SELECT * FROM mart.rfm_snapshots WHERE kind = 'backtest';

-- mart.rfm_summary: one row per segment. Backtest rates are measured on past snapshots, the
-- same-season snapshot (1 December 2010, quarter December to February) is the base case, and
-- the min and max across the five back-tests show how far the rate moves with the season.
CREATE OR REPLACE TABLE mart.rfm_summary AS
WITH per_snapshot AS (
    SELECT
        segment, snapshot_date,
        count(*)                                           AS customers,
        count(*) FILTER (WHERE bought_next_quarter)        AS repurchasers,
        avg(CAST(bought_next_quarter AS INTEGER))          AS repurchase_rate,
        avg(next_quarter_net_revenue)                      AS next_q_revenue_per_customer,
        avg(next_quarter_net_revenue) FILTER (WHERE bought_next_quarter) AS next_q_revenue_per_repurchaser,
        avg(monetary / 4.0)                                AS quarterly_run_rate
    FROM mart.rfm_backtest
    GROUP BY segment, snapshot_date
),
backtest AS (
    SELECT
        segment,
        max(customers)    FILTER (WHERE snapshot_date = (SELECT snapshot_date FROM dq.snapshots WHERE is_same_season)) AS same_season_customers,
        max(repurchasers) FILTER (WHERE snapshot_date = (SELECT snapshot_date FROM dq.snapshots WHERE is_same_season)) AS same_season_repurchasers,
        max(repurchase_rate) FILTER (WHERE snapshot_date = (SELECT snapshot_date FROM dq.snapshots WHERE is_same_season)) AS same_season_repurchase_rate,
        min(repurchase_rate)                                                  AS repurchase_rate_min,
        max(repurchase_rate)                                                  AS repurchase_rate_max,
        max(next_q_revenue_per_customer) FILTER (WHERE snapshot_date = (SELECT snapshot_date FROM dq.snapshots WHERE is_same_season)) AS same_season_next_q_revenue_per_customer,
        max(quarterly_run_rate) FILTER (WHERE snapshot_date = (SELECT snapshot_date FROM dq.snapshots WHERE is_same_season))          AS same_season_quarterly_run_rate
    FROM per_snapshot
    GROUP BY segment
),
pooled AS (
    SELECT segment,
           avg(CAST(bought_next_quarter AS INTEGER)) AS pooled_repurchase_rate,
           count(*)                                  AS pooled_customer_snapshots
    FROM mart.rfm_backtest
    GROUP BY segment
),
current_base AS (
    SELECT
        segment,
        count(*)                      AS customers,
        sum(monetary)                 AS trailing_12m_net_revenue,
        sum(monetary / 4.0)           AS quarterly_run_rate_total,
        avg(recency_days)             AS avg_recency_days,
        avg(frequency)                AS avg_frequency
    FROM mart.rfm
    GROUP BY segment
)
SELECT
    c.segment,
    c.customers,
    c.customers * 1.0 / sum(c.customers) OVER ()                 AS customer_share,
    c.trailing_12m_net_revenue,
    c.trailing_12m_net_revenue / sum(c.trailing_12m_net_revenue) OVER () AS revenue_share,
    c.avg_recency_days, c.avg_frequency,
    b.same_season_customers, b.same_season_repurchasers,
    b.same_season_repurchase_rate,
    1 - b.same_season_repurchase_rate                            AS same_season_lapse_rate,
    b.repurchase_rate_min, b.repurchase_rate_max,
    p.pooled_repurchase_rate,
    b.same_season_next_q_revenue_per_customer,
    -- Expected quarterly value of the customers who are likely to go quiet:
    -- segment run-rate (trailing 12 month revenue / 4) x probability of lapsing.
    c.quarterly_run_rate_total * (1 - b.same_season_repurchase_rate) AS revenue_at_risk_next_quarter,
    c.quarterly_run_rate_total * (1 - p.pooled_repurchase_rate)      AS revenue_at_risk_pooled_rates
FROM current_base AS c
LEFT JOIN backtest AS b USING (segment)
LEFT JOIN pooled   AS p USING (segment)
ORDER BY revenue_at_risk_next_quarter DESC;
