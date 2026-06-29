---
language: python
tags: [pandas, groupby, merge, data-wrangling]
title: Pandas GroupBy, Merge, and Pivot
description: GroupBy aggregations, merge/join types, concat, pivot tables, and multi-index operations
source: pattern
---

```python
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

orders = pd.DataFrame({
    "order_id": [1, 2, 3, 4, 5],
    "customer": ["Alice", "Bob", "Alice", "Charlie", "Bob"],
    "product":  ["Widget", "Gadget", "Widget", "Gadget", "Doohickey"],
    "qty":      [2, 1, 3, 5, 2],
    "price":    [9.99, 24.99, 9.99, 24.99, 14.99],
})
orders["total"] = orders["qty"] * orders["price"]

customers = pd.DataFrame({
    "customer": ["Alice", "Bob", "Charlie", "Diana"],
    "city":     ["NYC", "LA", "Chicago", "NYC"],
    "tier":     ["Gold", "Silver", "Gold", "Bronze"],
})

# ---------------------------------------------------------------------------
# groupby — split-apply-combine
# ---------------------------------------------------------------------------

# Single aggregation on one column
revenue_by_customer = orders.groupby("customer")["total"].sum()
print(revenue_by_customer)

# Multiple aggregations on one column
stats = orders.groupby("customer")["total"].agg(["sum", "mean", "count", "std"])
print(stats)

# Different aggregations per column
agg_dict = orders.groupby("customer").agg({
    "total": "sum",
    "qty":   "mean",
    "order_id": "nunique",
})
print(agg_dict)

# Named aggregations (pandas 0.25+)
named = orders.groupby("customer").agg(
    total_spent=("total", "sum"),
    avg_qty=("qty", "mean"),
    order_count=("order_id", "count"),
)
print(named)

# GroupBy with multiple columns → multi-index
by_customer_product = orders.groupby(["customer", "product"])["total"].sum()
print(by_customer_product)

# Reset index after groupby
flat = by_customer_product.reset_index()

# ---------------------------------------------------------------------------
# merge — SQL-style joins
# ---------------------------------------------------------------------------

# Inner join — only matching keys
inner = pd.merge(orders, customers, on="customer", how="inner")
print(inner)

# Left join — keep all rows from left (orders)
left = pd.merge(orders, customers, on="customer", how="left")
print(left)

# Outer join — keep all rows from both
outer = pd.merge(orders, customers, on="customer", how="outer")
print(outer)

# Merge on different column names
df_left = pd.DataFrame({"key": [1, 2], "val": ["a", "b"]})
df_right = pd.DataFrame({"k": [1, 3], "val2": ["x", "y"]})
merged = pd.merge(df_left, df_right, left_on="key", right_on="k", how="left")
print(merged)

# Merge with index
# pd.merge(df1, df2, left_index=True, right_index=True)

# ---------------------------------------------------------------------------
# concat — stacking rows or columns
# ---------------------------------------------------------------------------

q1 = pd.DataFrame({"product": ["A", "B"], "sales": [100, 200]})
q2 = pd.DataFrame({"product": ["A", "C"], "sales": [150, 250]})

# Vertically stack rows
combined = pd.concat([q1, q2], ignore_index=True)
print(combined)

# Horizontally join columns
by_col = pd.concat([q1, q2], axis=1)
print(by_col)

# ---------------------------------------------------------------------------
# pivot tables
# ---------------------------------------------------------------------------

# Simple pivot — index=rows, columns=cols, values=aggregated
pivot = orders.pivot_table(
    index="customer",
    columns="product",
    values="total",
    aggfunc="sum",
    fill_value=0,
)
print(pivot)

# Multiple values
pivot2 = orders.pivot_table(
    index="customer",
    values=["total", "qty"],
    aggfunc="sum",
)
print(pivot2)

# Margins (grand total row/column)
pivot3 = orders.pivot_table(
    index="customer",
    columns="product",
    values="total",
    aggfunc="sum",
    margins=True,
    margins_name="Total",
)
print(pivot3)

# melt — unpivot (wide → long)
wide = pd.DataFrame({
    "name": ["Alice", "Bob"],
    "math": [90, 85],
    "eng":  [88, 92],
    "sci":  [95, 78],
})
long = wide.melt(id_vars=["name"], var_name="subject", value_name="score")
print(long)

# ---------------------------------------------------------------------------
# Multi-index operations
# ---------------------------------------------------------------------------

# Create multi-index DataFrame
arrays = [["A", "A", "B", "B"], [1, 2, 1, 2]]
mi = pd.MultiIndex.from_arrays(arrays, names=["group", "sub"])
multi_df = pd.DataFrame({"value": [10, 20, 30, 40]}, index=mi)
print(multi_df)

# Access with tuple
print(multi_df.loc[("A", 1)])

# Cross-section at a level
print(multi_df.xs("A", level="group"))

# Stack / unstack
stacked = wide.set_index("name").stack().reset_index()
stacked.columns = ["name", "subject", "score"]
print(stacked)
```