# Data quality decisions

Generated from `dq.rule_log` (see `sql/20_dq_flags.sql` and `sql/22_dq_log.sql`). Each raw row gets one verdict: kept, or removed by the first matching rule below, in this order.

Raw rows: 1,067,371. Rows kept: 996,172 (93.3%).

| # | Rule | Action | Rows | % of raw | Revenue affected | Decision |
| ---: | :--- | :--- | ---: | ---: | ---: | :--- |
| 1 | `cross_sheet_overlap_copy` | excluded | 22,523 | 2.11% | £377k | The workbook has two sheets that both contain 1 to 9 December 2010. Invoices found in both sheets are identical line for line, so the copy in the later sheet is dropped. |
| 2 | `exact_duplicate_line` | excluded | 11,812 | 1.11% | £54k | A line identical to an earlier line on the same invoice in every field (product, quantity, price, timestamp, customer, country) is treated as a double entry and dropped. A genuine repeat scan would also be dropped, so revenue can be slightly understated. |
| 3 | `non_merchandise_charge` | excluded | 5,799 | 0.54% | -£72k | Postage, carriage, bank and marketplace fees, manual and discount lines, bad-debt adjustments, gift vouchers and test products are not product sales. They are removed so revenue means merchandise revenue. |
| 4 | `unparseable_or_zero_quantity` | excluded | 0 | 0.00% | n/a | A value that cannot be read as a number or date, or a zero quantity. None are expected; the rule exists so a corrupt row cannot slip through silently. |
| 5 | `sign_conflict` | excluded | 3,393 | 0.32% | £0 | Negative quantity on a normal invoice (stock write-offs, damages and lost items, which carry price 0 and no customer) or positive quantity on a cancellation invoice. These are inventory events, not customer sales or returns. |
| 6 | `nonpositive_price` | excluded | 2,572 | 0.24% | £0 | A price of zero or below (free items and stock corrections) carries no revenue and would distort basket size and unit counts. |
| 7 | `outside_analysis_window` | excluded | 25,100 | 2.35% | £440k | December 2011 stops on the 9th. A partial month would look like a sales collapse, so the analysis covers the 24 complete months from December 2009 to November 2011. |
| 10 | `missing_customer_id` | kept and flagged | 219,299 | 20.55% | £2.47M | Guest checkouts have no customer ID. They stay in revenue, orders and product KPIs but cannot be followed over time, so they are left out of cohorts and RFM. |
| 11 | `return_lines_kept` | kept and flagged | 17,568 | 1.65% | -£542k | Cancellation invoices (invoice number starts with C) are returns or order reversals. They are kept as negative revenue on the cancellation date, so revenue is net of returns. |
| 12 | `large_quantity_kept` | kept and flagged | 36 | 0.00% | £51k | Lines with an absolute quantity at or above the threshold in dq.params are flagged, not dropped. Some are reversed by a cancellation shortly after and net out of revenue; the rest look like genuine wholesale orders. |
| 13 | `missing_description` | kept and flagged | 4,382 | 0.41% | £0 | Rows with no product description, counted before any other rule. A missing description does not affect revenue; where one survives cleaning, the product name shown is the most common description for its stock code, or the code itself. |
| 14 | `stock_code_case_normalised` | normalised | 3,472 | 0.33% | £57k | Stock codes are trimmed and upper-cased so that "m" and "M" are one code. |
| 15 | `description_whitespace_trimmed` | normalised | 213,035 | 19.96% | £3.69M | Leading and trailing spaces are trimmed from descriptions. |
| 16 | `customer_in_two_countries` | normalised | 12 | 0.00% | n/a | Customers whose kept lines carry more than one country (a count of customers, not rows). Each is assigned the country of their first sale so customer counts add up across countries. |

Revenue affected is quantity x price on the affected rows. Rules 10 to 13 describe rows that stay in the data; rules 14 to 16 describe normalisation, not removal.

## Revenue bridge

| Step | Rows | Revenue |
| :--- | ---: | ---: |
| raw file | 1,067,371 | £19.29M |
| cross sheet overlap copy | -22,523 | -£377.49k |
| exact duplicate line | -11,812 | -£54.23k |
| non merchandise charge | -5,799 | £71.87k |
| unparseable or zero quantity | +0 | £0 |
| sign conflict | -3,393 | £0 |
| nonpositive price | -2,572 | £0 |
| outside analysis window | -25,100 | -£440.40k |
| kept (clean.lines) | 996,172 | £18.49M |

Removing non-merchandise lines raises revenue because most of them (manual adjustments, bank and marketplace fees, bad debt) were negative.
