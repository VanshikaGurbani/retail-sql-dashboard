"""Write notebooks/01_exploratory_analysis.ipynb (without outputs).

    python scripts/build_notebooks.py        # then: retail run-notebooks

The notebook is generated so its text lives in reviewable Python. Numbers in the prose are
produced by code cells (display(Markdown(f"..."))); the static markdown contains no figures.
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parent.parent
cells = []


def md(text: str) -> None:
    cells.append(nbf.v4.new_markdown_cell(text.strip()))


def code(text: str) -> None:
    cells.append(nbf.v4.new_code_cell(text.strip()))


md(
    """
# Exploratory analysis: what the raw retail data looks like, and why the SQL does what it does

**Question this notebook answers.** Before building a retention analysis, what is wrong or surprising in the
Online Retail II transactions, and which of those things must the SQL layer handle?

Each section looks at one issue (missing values, distributions, outliers, returns, duplicates, non-product
lines), shows the evidence, and ends with the rule in `sql/` that it motivated. Every number here is computed
by a query or by code in this notebook. The cleaned results are in `docs/RESULTS.md`.

Data: UCI Online Retail II, UK online gift-ware retailer, December 2009 to December 2011, licence CC BY 4.0.
Revenue means quantity times price in pounds. It is not profit.
"""
)

code(
    """
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from IPython.display import Markdown, display

from retail import nb

nb.apply_style()
pd.options.display.float_format = "{:,.2f}".format
pd.options.display.width = 140
con = nb.connect()
P = nb.P
nb.banner()
"""
)

md("## 1. Shape and coverage")
code(
    """
shape = nb.sql(
    con,
    '''SELECT count(*) AS rows, count(DISTINCT invoice_no) AS invoices,
              count(DISTINCT stock_code) AS stock_codes, count(DISTINCT customer_id) AS customers,
              count(DISTINCT country) AS countries,
              min(invoice_ts) AS first_timestamp, max(invoice_ts) AS last_timestamp
       FROM stg.transactions''',
)
display(shape.T.rename(columns={0: "value"}))
by_sheet = nb.sql(
    con,
    '''SELECT sheet, count(*) AS rows, min(invoice_ts) AS first_timestamp, max(invoice_ts) AS last_timestamp
       FROM stg.transactions GROUP BY sheet ORDER BY sheet''',
)
display(by_sheet)
"""
)
md(
    """
The file is a workbook with two sheets, one per trading year. The date ranges above show the sheets do not
meet end to end: they **overlap**. That is checked properly in section 6.

| Column | Meaning | Type used in staging |
|---|---|---|
| Invoice | Invoice number; starts with C for a cancellation | text, plus a boolean flag |
| StockCode | Product code, with a few non-product codes mixed in | upper-cased text |
| Description | Product name | text, trimmed |
| Quantity | Units on the line; negative on cancellations | integer |
| InvoiceDate | Timestamp of the invoice | timestamp |
| Price | Unit price in pounds | DECIMAL(12,4) |
| Customer ID | Customer number; often empty | integer |
| Country | Country of the customer | text |
"""
)

md("## 2. Missing values")
code(
    """
cols = ["invoice_no", "stock_code", "description", "quantity", "invoice_ts", "unit_price", "customer_id", "country"]
parts = [
    f"SELECT '{c}' AS column_name, count(*) FILTER (WHERE {c} IS NULL OR trim({c}) = '') AS missing, count(*) AS total FROM raw.online_retail"
    for c in cols
]
miss = nb.sql(con, " UNION ALL ".join(parts))
miss["missing_share"] = miss.missing / miss.total
display(miss)

fig, ax = plt.subplots(figsize=(7, 3.2))
m = miss.sort_values("missing_share")
ax.barh(m.column_name, m.missing_share * 100, color=P["blue"])
for y, v in enumerate(m.missing_share * 100):
    ax.text(v + 0.3, y, f"{v:.1f}%", va="center")
ax.set_xlabel("Share of rows with the value missing (%)")
worst = miss.sort_values("missing_share").iloc[-1]
ax.set_title(f"{worst.column_name} is the main gap: {worst.missing_share:.0%} of rows")
plt.show()
"""
)
code(
    """
guest = nb.sql(
    con,
    '''SELECT s.sheet, count(*) AS rows,
              avg(CAST(customer_id IS NULL AS INTEGER)) AS share_rows_without_customer,
              sum(line_value) FILTER (WHERE customer_id IS NULL) / sum(line_value) AS share_revenue_without_customer
       FROM stg.transactions s WHERE quantity > 0 AND unit_price > 0 OR is_cancellation GROUP BY s.sheet ORDER BY s.sheet''',
)
display(guest)
trend = nb.sql(
    con,
    '''SELECT date_trunc('month', invoice_ts) AS month,
              avg(CAST(customer_id IS NULL AS INTEGER)) AS guest_row_share
       FROM stg.transactions WHERE quantity > 0 AND unit_price > 0 GROUP BY 1 ORDER BY 1''',
)
fig, ax = plt.subplots(figsize=(9, 3.2))
ax.plot(trend.month, trend.guest_row_share * 100, color=P["orange"], lw=2.5)
ax.set_ylabel("% of sale lines with no customer ID")
hi = trend.loc[trend.guest_row_share.idxmax()]
ax.set_title(f"Guest checkouts peak in {hi.month:%B %Y} at {hi.guest_row_share:.0%} of lines")
plt.show()
"""
)
md(
    """
**What this means.** Customer ID is the only column with a large gap, and the gap is not constant: the share of
lines without one swings from month to month (chart above). Rows without a customer cannot be followed over
time, so they cannot be part of cohorts or RFM, but they are real sales and must stay in revenue. That is the
rule in `sql/22_dq_log.sql` (`missing_customer_id`: kept and flagged) and the reason customer KPIs and revenue
KPIs are defined separately in `docs/KPI_DEFINITIONS.md`.
"""
)

md("## 3. Distributions")
code(
    """
sales = nb.sql(
    con,
    '''SELECT quantity, unit_price, quantity * unit_price AS line_value
       FROM stg.transactions WHERE quantity > 0 AND unit_price > 0''',
)
pct = sales.quantile([0.01, 0.25, 0.5, 0.75, 0.99, 0.999]).T
pct.columns = ["p1", "p25", "median", "p75", "p99", "p99.9"]
pct["max"] = sales.max()
display(pct)

fig, axes = plt.subplots(1, 3, figsize=(12, 3.4))
for ax, col, label, colour in zip(
    axes,
    ["quantity", "unit_price", "line_value"],
    ["Units per line", "Unit price (£)", "Line value (£)"],
    [P["blue"], P["orange"], P["green"]],
):
    ax.hist(np.log10(sales[col]), bins=60, color=colour)
    ticks = [t for t in range(-3, 6) if sales[col].min() <= 10**t <= sales[col].max() * 3]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{10.0**t:g}" for t in ticks])
    ax.set_xlabel(label + " (log scale)")
axes[0].set_ylabel("Lines")
axes[1].set_title("All three are heavily right-skewed")
plt.tight_layout()
plt.show()
"""
)
code(
    """
orders = nb.sql(
    con,
    '''SELECT invoice_no, sum(line_value) AS order_value, count(*) AS n_lines
       FROM clean.lines WHERE line_type = 'sale' GROUP BY invoice_no''',
)
display(Markdown(
    f"Across {len(orders):,} sale invoices the mean order value is **£{orders.order_value.mean():,.0f}** but the "
    f"median is **£{orders.order_value.median():,.0f}**, and the 99th percentile is "
    f"**£{orders.order_value.quantile(0.99):,.0f}**. The mean sits well above the median because a few very large "
    "orders pull it up, so the dashboard shows basket size as revenue per order and the memo avoids leaning on "
    "the mean alone."
))
top_share = orders.sort_values("order_value", ascending=False).order_value.cumsum() / orders.order_value.sum()
k = int(len(orders) * 0.01)
display(Markdown(f"The largest 1% of orders ({k:,} invoices) carry **{top_share.iloc[k - 1]:.0%}** of order revenue."))
"""
)
md(
    """
**What this means.** Quantities and prices span several orders of magnitude (the retailer sells to wholesalers
as well as individuals), so means mislead and thresholds must be explicit. The cleaning rules therefore do not
trim by percentile; they remove only rows that are impossible or are not product sales, and large values are
flagged rather than dropped (section 4).
"""
)

md("## 4. Outliers")
code(
    """
big = nb.sql(
    con,
    '''SELECT invoice_no, invoice_ts, stock_code, description, quantity, unit_price, customer_id, line_value
       FROM stg.transactions ORDER BY abs(quantity) DESC LIMIT 8''',
)
display(big)
thr = con.execute("SELECT large_qty_threshold FROM dq.params").fetchone()[0]
flag = nb.sql(
    con,
    '''SELECT count(*) AS lines_flagged,
              sum(line_value) FILTER (WHERE line_type = 'sale') AS flagged_sales,
              sum(line_value) FILTER (WHERE line_type = 'return') AS flagged_returns,
              (SELECT sum(line_value) FROM clean.lines) AS total_net_revenue
       FROM clean.lines WHERE is_large_quantity''',
).iloc[0]
display(Markdown(
    f"With a threshold of {thr:,} units there are **{int(flag.lines_flagged)}** flagged lines in the cleaned data. "
    f"They carry £{flag.flagged_sales:,.0f} of sales and £{abs(flag.flagged_returns):,.0f} of returns, "
    f"which is **{(flag.flagged_sales + flag.flagged_returns) / flag.total_net_revenue:.2%}** of net revenue."
))
"""
)
code(
    """
paired = nb.sql(
    con,
    '''WITH big_sales AS (
           SELECT * FROM clean.lines WHERE is_large_quantity AND line_type = 'sale' AND customer_id IS NOT NULL
       )
       SELECT b.invoice_no, b.customer_id, b.stock_code, b.quantity AS sold_units,
              any_value(r.quantity) AS returned_units, b.line_value AS sold_value,
              any_value(r.invoice_date) - b.invoice_date AS days_to_return
       FROM big_sales b
       LEFT JOIN clean.lines r
         ON r.line_type = 'return' AND r.customer_id = b.customer_id AND r.stock_code = b.stock_code
        AND r.quantity = -b.quantity AND r.invoice_date BETWEEN b.invoice_date AND b.invoice_date + 30
       GROUP BY b.invoice_no, b.customer_id, b.stock_code, b.quantity, b.line_value, b.invoice_date
       ORDER BY b.line_value DESC''',
)
reversed_ = paired.returned_units.notna()
display(paired.head(8))
display(Markdown(
    f"**{int(reversed_.sum())} of the {len(paired)} large sale lines** from identified customers are reversed in full by the "
    "same customer within 30 days. Those pairs cancel out of net revenue, which is why the SQL keeps both sides "
    "and flags them instead of deleting the sale and leaving the cancellation behind."
))
"""
)
md(
    """
**What this means.** The very largest quantities include order mistakes that were reversed on a later invoice
(the table above shows which large sales have a matching return). Dropping only the sale would overstate returns;
dropping only the cancellation would overstate sales. Keeping both nets them to zero. The other large lines
look like genuine wholesale orders, so the rule (`large_quantity_kept` in `sql/22_dq_log.sql`) flags them for
review and keeps them. The sensitivity above shows how little net revenue the flagged lines carry.
"""
)

md("## 5. A first look at returns")
code(
    """
monthly = nb.sql(con, "SELECT month, sales_revenue, returns_value, return_rate FROM mart.monthly ORDER BY month")
ret_inv = nb.sql(
    con,
    '''SELECT count(*) FILTER (WHERE order_type = 'return') AS return_invoices,
              count(*) AS invoices,
              count(*) FILTER (WHERE order_type = 'return') * 1.0 / count(*) AS return_invoice_share
       FROM mart.orders''',
).iloc[0]
fig, ax = plt.subplots(figsize=(9, 3.4))
ax.bar(monthly.month.astype(str).str[:7], monthly.return_rate * 100, color=P["vermillion"])
ax.set_xticks(range(0, len(monthly), 2))
ax.set_xticklabels(monthly.month.astype(str).str[:7].iloc[::2], rotation=45, ha="right")
ax.set_ylabel("Returns as % of sales value")
peak = monthly.loc[monthly.return_rate.idxmax()]
ax.set_title(f"Returns are small most months; {peak.month:%B %Y} peaks at {peak.return_rate:.1%} of sales")
plt.show()
display(Markdown(
    f"Cancellation invoices are **{ret_inv.return_invoice_share:.1%}** of all invoices ({int(ret_inv.return_invoices):,} of "
    f"{int(ret_inv.invoices):,})."
))
"""
)
code(
    """
prod = nb.sql(
    con,
    '''SELECT stock_code, description, sales_revenue, returns_value, return_rate
       FROM mart.products WHERE sales_revenue >= 20000 ORDER BY return_rate DESC LIMIT 8''',
)
display(prod)
lag = nb.sql(
    con,
    '''SELECT count(*) AS returns_from_identified_customers,
              avg(CAST(customer_id IS NULL AS INTEGER)) AS share_without_customer
       FROM clean.lines WHERE line_type = 'return' ''',
).iloc[0]
display(Markdown(
    f"Of **{int(lag.returns_from_identified_customers):,}** return lines in the cleaned data, "
    f"{lag.share_without_customer:.1%} have no customer ID, so almost all returns can be attributed to a customer. "
    "The file does not say which invoice a return belongs to, so a return cannot be tied back to its original sale."
))
"""
)
md(
    """
**What this means.** Returns are a small share of sales in most months. The spikes trace back to a single
customer or invoice (the reversed order from section 4 is the largest), not to a general rise, and one product
is almost entirely returned for that reason. The SQL therefore keeps cancellation invoices as **negative revenue
on the date of cancellation** (`return_lines_kept`), defines revenue as net of returns, and defines an active
customer by purchases only, so a return does not make someone "active". The limitation is stated in the README:
returns cannot be matched to the original order.
"""
)

md("## 6. Duplicates and the overlap between the sheets")
code(
    """
ov = nb.sql(
    con,
    '''WITH inv AS (SELECT invoice_no, count(DISTINCT sheet) AS n FROM stg.transactions GROUP BY invoice_no)
       SELECT count(*) FILTER (WHERE n > 1) AS invoices_in_both_sheets,
              count(*) AS invoices FROM inv''',
).iloc[0]
same = nb.sql(
    con,
    '''WITH both_inv AS (SELECT invoice_no FROM stg.transactions GROUP BY invoice_no HAVING count(DISTINCT sheet) > 1),
            a AS (SELECT invoice_no, stock_code, description, quantity, invoice_ts, unit_price, customer_id, country
                  FROM stg.transactions WHERE invoice_no IN (SELECT invoice_no FROM both_inv)
                    AND sheet = (SELECT min(sheet) FROM stg.transactions)),
            b AS (SELECT invoice_no, stock_code, description, quantity, invoice_ts, unit_price, customer_id, country
                  FROM stg.transactions WHERE invoice_no IN (SELECT invoice_no FROM both_inv)
                    AND sheet = (SELECT max(sheet) FROM stg.transactions))
       SELECT (SELECT count(*) FROM a) AS lines_in_first_sheet, (SELECT count(*) FROM b) AS lines_in_second_sheet,
              (SELECT count(*) FROM (SELECT * FROM a EXCEPT ALL SELECT * FROM b)) AS only_in_first,
              (SELECT count(*) FROM (SELECT * FROM b EXCEPT ALL SELECT * FROM a)) AS only_in_second''',
).iloc[0]
display(Markdown(
    f"**{int(ov.invoices_in_both_sheets):,}** invoices appear in both sheets ({int(same.lines_in_first_sheet):,} lines in the first, "
    f"{int(same.lines_in_second_sheet):,} in the second). Lines that differ between the copies: "
    f"**{int(same.only_in_first)}** only in the first, **{int(same.only_in_second)}** only in the second."
))
log = nb.sql(con, "SELECT rule, n_rows, revenue FROM dq.rule_log WHERE rule IN ('cross_sheet_overlap_copy', 'exact_duplicate_line')")
display(log)
"""
)
md(
    """
**What this means.** The copies are identical, so keeping both would double count a block of days and inflate
December 2010. The SQL drops the later sheet's copy (`cross_sheet_overlap_copy`). Separately, some lines
repeat exactly within an invoice. They are treated as double entries and dropped (`exact_duplicate_line`); a
genuine repeat scan would also be dropped, which is why that rule's effect on revenue is reported rather than
hidden.
"""
)

md("## 7. Lines that are not product sales")
code(
    """
nm = nb.sql(
    con,
    '''SELECT non_merch_type, count(*) AS rows, sum(line_value) AS revenue, min(stock_code) AS example_code
       FROM stg.transactions_flagged WHERE non_merch_type IS NOT NULL AND dq_reason = 'non_merchandise_charge'
       GROUP BY 1 ORDER BY abs(sum(line_value)) DESC''',
)
display(nm)
sc = nb.sql(
    con,
    '''SELECT quantity < 0 AS negative_quantity, NOT is_cancellation AS normal_invoice, unit_price = 0 AS zero_price,
              customer_id IS NULL AS no_customer, count(*) AS rows
       FROM stg.transactions_flagged WHERE dq_reason = 'sign_conflict' GROUP BY ALL ORDER BY rows DESC''',
)
display(sc)
"""
)
md(
    """
**What this means.** Postage, fees, manual adjustments, bad-debt entries, gift vouchers and test products sit in
the same column as products. Several carry large negative values, so leaving them in would make revenue
unreliable and product rankings meaningless. They are removed from merchandise revenue (`non_merchandise_charge`)
and shown in the revenue bridge so nothing disappears silently. Negative quantities on normal invoices are
zero-price stock write-offs with no customer in this file (table above), not sales, and are removed under `sign_conflict`.
"""
)

md("## 8. From findings to rules, and a reconciliation")
code(
    """
rules = nb.sql(con, "SELECT rule_order, rule, kind, n_rows, share_of_raw_rows FROM dq.rule_log ORDER BY rule_order")
rules["share_of_raw_rows"] = (rules.share_of_raw_rows * 100).round(2).astype(str) + "%"
display(rules)
bridge = nb.sql(con, "SELECT step, label, n_rows, revenue FROM mart.revenue_bridge ORDER BY step")
display(bridge)
raw_rows = con.execute("SELECT count(*) FROM raw.online_retail").fetchone()[0]
kept = con.execute("SELECT count(*) FROM clean.lines").fetchone()[0]
excluded = con.execute("SELECT sum(n_rows) FROM dq.rule_log WHERE kind = 'excluded'").fetchone()[0]
assert kept + excluded == raw_rows, "row bridge does not reconcile"
raw_rev = con.execute("SELECT sum(quantity * unit_price) FROM stg.transactions").fetchone()[0]
bridge_total = bridge.revenue.iloc[:-1].sum()
assert abs(float(bridge_total) - float(bridge.revenue.iloc[-1])) < 0.01, "revenue bridge does not reconcile"
display(Markdown(
    f"Reconciled: {raw_rows:,} raw rows = {kept:,} kept + {int(excluded):,} removed, and the revenue bridge adds up to "
    f"£{float(bridge.revenue.iloc[-1]):,.2f} of kept revenue."
))
"""
)
md(
    """
## 9. A first look at the three business questions

These charts motivated the marts in `sql/30_` to `sql/36_`. The finished versions are in the dashboard
and in `docs/RESULTS.md`.
"""
)
code(
    """
m = nb.sql(con, "SELECT month, net_revenue, active_customers, orders_per_customer, net_revenue_per_order FROM mart.monthly ORDER BY month")
fig, axes = plt.subplots(1, 3, figsize=(13, 3.4))
x = m.month.astype(str).str[:7]
for ax, col, label, colour in zip(
    axes,
    ["active_customers", "orders_per_customer", "net_revenue_per_order"],
    ["Active customers", "Orders per customer", "Net revenue per order (£)"],
    [P["blue"], P["orange"], P["green"]],
):
    ax.plot(x, m[col], color=colour, lw=2.5)
    ax.set_xticks(range(0, len(m), 4))
    ax.set_xticklabels(x.iloc[::4], rotation=45, ha="right")
    ax.set_title(label)
plt.tight_layout()
plt.show()
once = con.execute("SELECT one_order_share FROM mart.headline").fetchone()[0]
display(Markdown(
    f"**{once:.0%}** of identified customers bought exactly once, so how many come back, and who, is the question "
    "the cohort and RFM tables answer."
))
"""
)
md(
    """
## What is weak

- Missing customer IDs are not random, so customer-level results describe identified customers only.
- Duplicate removal cannot tell a double entry from a genuine repeat scan.
- Returns cannot be linked to the original sale, so a return is dated when it was cancelled, not when it was sold.
- Prices and quantities have no cost, margin or discount fields, so nothing here says anything about profit.
- One retailer, two years: seasonality is seen twice at most.
"""
)

nb = nbf.v4.new_notebook()
nb.cells = cells
nb.metadata = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}
out = ROOT / "notebooks" / "01_exploratory_analysis.ipynb"
out.parent.mkdir(exist_ok=True)
nbf.write(nb, out)
print(f"wrote {out}")
