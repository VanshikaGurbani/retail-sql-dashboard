-- Staging: correct types and light normalisation only. No row is removed in this file.
-- TRY_CAST turns an unparseable value into NULL instead of failing; the tests assert that
-- no value that was present in the raw file became NULL by accident.
CREATE OR REPLACE TABLE stg.transactions AS
SELECT
    raw_row_id,
    sheet,
    trim(invoice_no)                                  AS invoice_no,
    starts_with(upper(trim(invoice_no)), 'C')         AS is_cancellation,
    upper(trim(stock_code))                           AS stock_code,   -- 'm' and 'M' are one code
    nullif(trim(description), '')                     AS description,
    TRY_CAST(quantity AS INTEGER)                     AS quantity,
    TRY_CAST(invoice_ts AS TIMESTAMP)                 AS invoice_ts,
    TRY_CAST(unit_price AS DECIMAL(12, 4))            AS unit_price,
    TRY_CAST(TRY_CAST(nullif(trim(customer_id), '') AS DOUBLE) AS INTEGER) AS customer_id,
    nullif(trim(country), '')                         AS country,
    TRY_CAST(quantity AS INTEGER) * TRY_CAST(unit_price AS DECIMAL(12, 4)) AS line_value
FROM raw.online_retail;
