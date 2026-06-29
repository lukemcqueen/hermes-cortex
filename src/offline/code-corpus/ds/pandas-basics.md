---
language: python
tags: [pandas, dataframe, data-science, python]
title: Pandas Basics
description: DataFrame creation, reading CSV/JSON/Excel, inspection, column selection, filtering, and handling NaN
source: pattern
---

```python
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# DataFrame creation
# ---------------------------------------------------------------------------

# From a dictionary
df = pd.DataFrame({
    "name": ["Alice", "Bob", "Charlie", "Diana"],
    "age":  [25, 30, 35, 28],
    "city": ["NYC", "LA", "Chicago", "NYC"],
    "salary": [70000, 80000, 95000, np.nan],
})
print(df)

# From a list of dicts
rows = [
    {"product": "Widget", "price": 9.99, "qty": 100},
    {"product": "Gadget", "price": 24.99, "qty": 50},
    {"product": "Doohickey", "price": 14.99, "qty": np.nan},
]
df2 = pd.DataFrame(rows)

# ---------------------------------------------------------------------------
# Reading external files
# ---------------------------------------------------------------------------

# CSV
# df = pd.read_csv("data.csv")
# df = pd.read_csv("data.csv", encoding="utf-8", parse_dates=["date"])

# JSON
# df = pd.read_json("data.json")

# Excel (requires openpyxl or xlrd)
# df = pd.read_excel("data.xlsx", sheet_name="Sheet1")

# ---------------------------------------------------------------------------
# Quick inspection
# ---------------------------------------------------------------------------

print(df.head(2))           # First 2 rows
print(df.info())            # Column dtypes, non-null counts, memory usage
print(df.describe())        # Summary stats for numeric columns
print(df.shape)             # (rows, columns)
print(df.columns.tolist())  # Column names
print(df.dtypes)            # Data types per column

# ---------------------------------------------------------------------------
# Column selection
# ---------------------------------------------------------------------------

# Single column → Series
names = df["name"]

# Multiple columns → DataFrame
subset = df[["name", "salary"]]

# Selection by data type
numeric_cols = df.select_dtypes(include=[np.number])

# ---------------------------------------------------------------------------
# Filtering rows
# ---------------------------------------------------------------------------

# Boolean mask
adults = df[df["age"] >= 30]

# Multiple conditions
nyc_high_earners = df[(df["city"] == "NYC") & (df["salary"] > 60000)]

# Using .isin()
cities = df[df["city"].isin(["NYC", "Chicago"])]

# Using .query() — handy for string-based filters
result = df.query("age > 28 and city == 'NYC'")

# ---------------------------------------------------------------------------
# Handling NaN (missing values)
# ---------------------------------------------------------------------------

# Check for nulls
print(df.isnull().sum())            # Count nulls per column
print(df.isna().any())              # Which columns have any null?

# Drop rows with any NaN
df_dropped = df.dropna()

# Drop rows where ALL values are NaN
df_dropped_all = df.dropna(how="all")

# Fill NaN with a constant
df_filled = df.fillna(0)

# Fill NaN with column mean
df["salary"] = df["salary"].fillna(df["salary"].mean())

# Forward-fill / backward-fill
df_ffill = df.fillna(method="ffill")
df_bfill = df.fillna(method="bfill")

# Interpolate (linear by default)
df_interp = df.interpolate()

# ---------------------------------------------------------------------------
# Setting a column as index
# ---------------------------------------------------------------------------
df_indexed = df.set_index("name")
print(df_indexed.loc["Alice"])  # Row access by label
```