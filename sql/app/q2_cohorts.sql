-- Retention by acquisition month and months since first purchase. Parameters: $start, $end
-- (the cohort month must fall in the range), $countries. The first cohort (December 2009)
-- is excluded: it includes customers who were already buying before the file starts.
SELECT
    cohort_month,
    month_offset,
    sum(cohort_size)                                  AS cohort_size,
    sum(active_customers)                             AS active_customers,
    sum(active_customers) * 1.0 / sum(cohort_size)    AS retention_rate
FROM cohorts
WHERE NOT is_first_window_cohort
  AND cohort_month BETWEEN date_trunc('month', CAST($start AS DATE)) AND date_trunc('month', CAST($end AS DATE))
  AND list_contains($countries, country)
GROUP BY cohort_month, month_offset
ORDER BY cohort_month, month_offset;
