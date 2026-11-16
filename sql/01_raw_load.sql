-- Load the flattened workbook as text. Nothing is typed, trimmed or dropped here.
-- raw_row_id is the row order of the file (preserve_insertion_order is on by default),
-- which makes "keep the first copy" rules deterministic.
CREATE OR REPLACE TABLE raw.online_retail AS
SELECT
    row_number() OVER () AS raw_row_id,
    sheet, invoice_no, stock_code, description, quantity, invoice_ts, unit_price, customer_id, country
FROM read_csv(
    '{{RAW_CSV}}',
    header = true,
    all_varchar = true,
    names = ['sheet', 'invoice_no', 'stock_code', 'description', 'quantity',
             'invoice_ts', 'unit_price', 'customer_id', 'country']
);
