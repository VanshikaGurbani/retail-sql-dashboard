-- Revenue by country for the chosen dates. Parameters: $start, $end, $countries.
SELECT
    country,
    sum(order_value)                                                 AS net_revenue,
    count(*) FILTER (WHERE order_type = 'sale')                      AS orders,
    count(DISTINCT customer_id) FILTER (WHERE order_type = 'sale')   AS customers
FROM orders
WHERE invoice_date BETWEEN $start AND $end
  AND list_contains($countries, country)
GROUP BY country
ORDER BY net_revenue DESC
LIMIT 10;
