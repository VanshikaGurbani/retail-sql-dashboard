-- Monthly revenue and its three drivers (identified customers): customers x orders per
-- customer x revenue per order. Parameters: $start, $end, $countries.
SELECT
    invoice_month AS month,
    sum(order_value)                                                       AS net_revenue,
    count(DISTINCT customer_id) FILTER (WHERE order_type = 'sale')         AS active_customers,
    count(*) FILTER (WHERE order_type = 'sale')                            AS orders,
    count(*) FILTER (WHERE order_type = 'sale' AND customer_id IS NOT NULL) * 1.0
        / nullif(count(DISTINCT customer_id) FILTER (WHERE order_type = 'sale'), 0) AS orders_per_customer,
    sum(order_value) FILTER (WHERE customer_id IS NOT NULL)
        / nullif(count(*) FILTER (WHERE order_type = 'sale' AND customer_id IS NOT NULL), 0) AS revenue_per_order
FROM orders
WHERE invoice_date BETWEEN $start AND $end
  AND list_contains($countries, country)
GROUP BY invoice_month
ORDER BY month;
