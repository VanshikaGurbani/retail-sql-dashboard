-- Top products by net revenue in the chosen months and countries. Parameters: $start, $end,
-- $countries. The OTHER bucket (products outside the top 500) is excluded from the ranking.
SELECT
    stock_code,
    any_value(description)                                   AS description,
    sum(net_revenue)                                         AS net_revenue,
    sum(units_sold)                                          AS units_sold,
    -sum(returns_value) / nullif(sum(sales_revenue), 0)      AS return_rate
FROM product_months_app
WHERE month BETWEEN date_trunc('month', CAST($start AS DATE)) AND date_trunc('month', CAST($end AS DATE))
  AND list_contains($countries, country)
  AND stock_code <> 'OTHER'
GROUP BY stock_code
ORDER BY net_revenue DESC
LIMIT 10;
