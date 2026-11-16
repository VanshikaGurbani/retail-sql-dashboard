-- Data quality. Every raw row receives exactly one verdict in dq_reason: NULL means kept,
-- otherwise the FIRST rule below that matches. The order matters and is documented in
-- docs/DATA_QUALITY.md (generated from dq.rule_log).
CREATE OR REPLACE TABLE stg.transactions_flagged AS
WITH invoice_sheets AS (
    SELECT invoice_no, count(DISTINCT sheet) AS n_sheets, max(sheet) AS last_sheet
    FROM stg.transactions
    GROUP BY invoice_no
),
step1 AS (
    SELECT t.*,
           -- the two workbook sheets share 1 to 9 December 2010; keep the copy in the first sheet
           (s.n_sheets > 1 AND t.sheet = s.last_sheet) AS is_overlap_copy
    FROM stg.transactions AS t
    JOIN invoice_sheets AS s USING (invoice_no)
),
step2 AS (
    SELECT *,
           row_number() OVER (
               PARTITION BY is_overlap_copy, invoice_no, stock_code, description, quantity,
                            invoice_ts, unit_price, customer_id, country
               ORDER BY raw_row_id
           ) AS dup_rank
    FROM step1
),
step3 AS (
    SELECT *,
           CASE
               WHEN stock_code IN ('POST', 'DOT', 'C2', 'CARRIAGE') THEN 'postage_carriage'
               WHEN stock_code IN ('BANK CHARGES', 'AMAZONFEE', 'CRUK') THEN 'platform_or_bank_fee'
               WHEN stock_code IN ('M', 'D', 'S', 'B', 'ADJUST', 'ADJUST2')
                    THEN 'manual_discount_or_adjustment'
               WHEN stock_code LIKE 'GIFT\_0001\_%' ESCAPE '\' THEN 'gift_voucher'
               WHEN stock_code LIKE 'TEST%' THEN 'test_product'
           END AS non_merch_type
    FROM step2
)
SELECT
    s.raw_row_id, s.sheet, s.invoice_no, s.is_cancellation, s.stock_code, s.description,
    s.quantity, s.invoice_ts, s.unit_price, s.customer_id, s.country, s.line_value,
    s.non_merch_type,
    CASE
        WHEN s.is_overlap_copy THEN 'cross_sheet_overlap_copy'
        WHEN s.dup_rank > 1 THEN 'exact_duplicate_line'
        WHEN s.non_merch_type IS NOT NULL THEN 'non_merchandise_charge'
        WHEN s.quantity IS NULL OR s.invoice_ts IS NULL OR s.unit_price IS NULL OR s.quantity = 0
             THEN 'unparseable_or_zero_quantity'
        WHEN s.is_cancellation <> (s.quantity < 0) THEN 'sign_conflict'
        WHEN s.unit_price <= 0 THEN 'nonpositive_price'
        WHEN s.invoice_ts < p.window_start OR s.invoice_ts >= p.window_end_excl
             THEN 'outside_analysis_window'
    END AS dq_reason
FROM step3 AS s
CROSS JOIN dq.params AS p;
