-- Headline KPIs for the chosen date range and countries. Parameters: $start, $end (dates),
-- $countries (list). Reads the exported order-level mart, so the app needs only exports/*.csv.
SELECT
    coalesce(sum(order_value), 0)                                        AS net_revenue,
    coalesce(sum(order_value) FILTER (WHERE order_type = 'sale'), 0)     AS sales_revenue,
    coalesce(sum(order_value) FILTER (WHERE order_type = 'return'), 0)   AS returns_value,
    count(*) FILTER (WHERE order_type = 'sale')                          AS orders,
    count(DISTINCT customer_id) FILTER (WHERE order_type = 'sale')       AS active_customers,
    count(*) FILTER (WHERE order_type = 'sale' AND customer_id IS NOT NULL) AS orders_identified,
    coalesce(sum(order_value) FILTER (WHERE customer_id IS NOT NULL), 0) AS net_revenue_identified,
    coalesce(sum(order_value) FILTER (WHERE customer_id IS NULL), 0)     AS net_revenue_guest
FROM orders
WHERE invoice_date BETWEEN $start AND $end
  AND list_contains($countries, country);
