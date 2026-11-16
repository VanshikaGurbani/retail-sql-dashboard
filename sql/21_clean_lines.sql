-- clean.lines: the rows every KPI is built from (dq_reason IS NULL).
-- A line is either a sale (positive quantity, normal invoice) or a return (negative quantity
-- on a cancellation invoice that starts with C). Returns stay in, as negative revenue on the
-- date of the cancellation; the file has no link from a return back to its original sale.

-- Home country: one country per identified customer (the country on their first sale), so
-- that customer counts add up across countries. A handful of customers appear under two
-- countries; dq.rule_log counts them.
CREATE OR REPLACE TABLE clean.customer_home_country AS
SELECT customer_id, country AS home_country
FROM (
    SELECT customer_id, country,
           row_number() OVER (PARTITION BY customer_id ORDER BY invoice_ts, raw_row_id) AS rn
    FROM stg.transactions_flagged
    WHERE dq_reason IS NULL AND customer_id IS NOT NULL AND NOT is_cancellation
)
WHERE rn = 1;

CREATE OR REPLACE TABLE clean.lines AS
SELECT
    f.raw_row_id,
    f.invoice_no,
    f.invoice_ts,
    CAST(f.invoice_ts AS DATE)                           AS invoice_date,
    CAST(date_trunc('month', f.invoice_ts) AS DATE)      AS invoice_month,
    f.stock_code,
    f.description,
    f.quantity,
    f.unit_price,
    f.line_value,
    CASE WHEN f.is_cancellation THEN 'return' ELSE 'sale' END AS line_type,
    f.customer_id,
    f.customer_id IS NULL                                AS is_anonymous,
    coalesce(h.home_country, f.country, 'Unknown')       AS country,
    abs(f.quantity) >= (SELECT large_qty_threshold FROM dq.params) AS is_large_quantity
FROM stg.transactions_flagged AS f
LEFT JOIN clean.customer_home_country AS h USING (customer_id)
WHERE f.dq_reason IS NULL;
