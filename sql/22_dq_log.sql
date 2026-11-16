-- dq.rule_log: one row per decision, with rows and revenue affected. docs/DATA_QUALITY.md is
-- generated from this table, so the documented counts cannot drift from the code.
CREATE OR REPLACE TABLE dq.rule_log AS
WITH exclusions AS (
    SELECT dq_reason AS rule, count(*) AS n_rows, sum(line_value) AS revenue
    FROM stg.transactions_flagged
    WHERE dq_reason IS NOT NULL
    GROUP BY dq_reason
),
notes AS (
    SELECT * FROM (VALUES
        (1, 'cross_sheet_overlap_copy', 'excluded',
         'The workbook has two sheets that both contain 1 to 9 December 2010. Invoices found in both sheets are identical line for line, so the copy in the later sheet is dropped.'),
        (2, 'exact_duplicate_line', 'excluded',
         'A line identical to an earlier line on the same invoice in every field (product, quantity, price, timestamp, customer, country) is treated as a double entry and dropped. A genuine repeat scan would also be dropped, so revenue can be slightly understated.'),
        (3, 'non_merchandise_charge', 'excluded',
         'Postage, carriage, bank and marketplace fees, manual and discount lines, bad-debt adjustments, gift vouchers and test products are not product sales. They are removed so revenue means merchandise revenue.'),
        (4, 'unparseable_or_zero_quantity', 'excluded',
         'A value that cannot be read as a number or date, or a zero quantity. None are expected; the rule exists so a corrupt row cannot slip through silently.'),
        (5, 'sign_conflict', 'excluded',
         'Negative quantity on a normal invoice (stock write-offs, damages and lost items, which carry price 0 and no customer) or positive quantity on a cancellation invoice. These are inventory events, not customer sales or returns.'),
        (6, 'nonpositive_price', 'excluded',
         'A price of zero or below (free items and stock corrections) carries no revenue and would distort basket size and unit counts.'),
        (7, 'outside_analysis_window', 'excluded',
         'December 2011 stops on the 9th. A partial month would look like a sales collapse, so the analysis covers the 24 complete months from December 2009 to November 2011.')
    ) AS t(rule_order, rule, kind, decision)
),
exclusion_rows AS (
    SELECT n.rule_order, n.rule, n.kind, e.n_rows, e.revenue, n.decision
    FROM notes AS n LEFT JOIN exclusions AS e USING (rule)
),
flags AS (
    SELECT 10 AS rule_order, 'missing_customer_id' AS rule, 'kept_and_flagged' AS kind,
           count(*) AS n_rows, sum(line_value) AS revenue,
           'Guest checkouts have no customer ID. They stay in revenue, orders and product KPIs but cannot be followed over time, so they are left out of cohorts and RFM.' AS decision
    FROM clean.lines WHERE is_anonymous
    UNION ALL
    SELECT 11, 'return_lines_kept', 'kept_and_flagged', count(*), sum(line_value),
           'Cancellation invoices (invoice number starts with C) are returns or order reversals. They are kept as negative revenue on the cancellation date, so revenue is net of returns.'
    FROM clean.lines WHERE line_type = 'return'
    UNION ALL
    SELECT 12, 'large_quantity_kept', 'kept_and_flagged', count(*), sum(line_value),
           'Lines with an absolute quantity at or above the threshold in dq.params are flagged, not dropped. Some are reversed by a cancellation shortly after and net out of revenue; the rest look like genuine wholesale orders.'
    FROM clean.lines WHERE is_large_quantity
    UNION ALL
    SELECT 13, 'missing_description', 'kept_and_flagged', count(*), sum(line_value),
           'Rows with no product description, counted before any other rule. A missing description does not affect revenue; where one survives cleaning, the product name shown is the most common description for its stock code, or the code itself.'
    FROM stg.transactions_flagged WHERE description IS NULL
    UNION ALL
    SELECT 14, 'stock_code_case_normalised', 'normalised', count(*), sum(t.line_value),
           'Stock codes are trimmed and upper-cased so that "m" and "M" are one code.'
    FROM stg.transactions AS t
    JOIN raw.online_retail AS r USING (raw_row_id)
    WHERE r.stock_code <> t.stock_code
    UNION ALL
    SELECT 15, 'description_whitespace_trimmed', 'normalised', count(*), sum(t.line_value),
           'Leading and trailing spaces are trimmed from descriptions.'
    FROM stg.transactions AS t
    JOIN raw.online_retail AS r USING (raw_row_id)
    WHERE r.description <> t.description
    UNION ALL
    SELECT 16, 'customer_in_two_countries', 'normalised', count(*), NULL,
           'Customers whose kept lines carry more than one country (a count of customers, not rows). Each is assigned the country of their first sale so customer counts add up across countries.'
    FROM (
        SELECT customer_id FROM stg.transactions_flagged
        WHERE dq_reason IS NULL AND customer_id IS NOT NULL
        GROUP BY customer_id HAVING count(DISTINCT country) > 1
    )
)
SELECT
    rule_order, rule, kind,
    coalesce(n_rows, 0) AS n_rows,
    coalesce(n_rows, 0) * 1.0 / (SELECT count(*) FROM raw.online_retail) AS share_of_raw_rows,
    revenue,
    decision
FROM exclusion_rows
UNION ALL
SELECT rule_order, rule, kind, n_rows,
       n_rows * 1.0 / (SELECT count(*) FROM raw.online_retail), revenue, decision
FROM flags
ORDER BY rule_order;
