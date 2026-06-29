---
language: python
tags: [pandas, apply, transform, vectorized]
title: Pandas Apply, Transform, and Vectorized Operations
description: Using apply, map, applymap, transform, rolling windows, custom functions, and understanding vectorized operations vs loops
source: pattern
---

```python
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

df = pd.DataFrame({
    "name":  ["Alice", "Bob", "Charlie", "Diana"],
    "score": [85, 92, 78, 95],
    "grade": ["B", "A", "C", "A"],
    "bonus": [5, 10, None, 8],
})

# ---------------------------------------------------------------------------
# .map() — Series only, element-wise substitution
# ---------------------------------------------------------------------------

# Replace values via dict
grade_points = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0}
df["gpa"] = df["grade"].map(grade_points)
print(df[["name", "grade", "gpa"]])

# Map with a function
df["score_label"] = df["score"].map(lambda x: "Pass" if x >= 70 else "Fail")

# ---------------------------------------------------------------------------
# .apply() — DataFrame or Series, flexible
# ---------------------------------------------------------------------------

# Apply a function to a column (Series)
df["score_squared"] = df["score"].apply(lambda x: x**2)

# Apply a function to each row (axis=1)
def categorize(row):
    if row["score"] >= 90:
        return "Excellent"
    elif row["score"] >= 80:
        return "Good"
    else:
        return "Needs Improvement"

df["category"] = df.apply(categorize, axis=1)

# Apply a function to each column (axis=0)
col_ranges = df[["score", "bonus"]].apply(lambda col: col.max() - col.min())
print(col_ranges)

# Apply with additional arguments
def scale(x, factor=1):
    return x * factor

df["score_scaled"] = df["score"].apply(scale, factor=1.1)

# ---------------------------------------------------------------------------
# .applymap() — element-wise on entire DataFrame (deprecated in 2.1+, use .map())
# ---------------------------------------------------------------------------

# Format all numeric values (DataFrame-wide)
# df_formatted = df[["score", "bonus"]].applymap(lambda x: f"{x:.1f}")

# Modern equivalent: .map() on DataFrame
df_formatted = df[["score", "bonus"]].map(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
print(df_formatted)

# ---------------------------------------------------------------------------
# .transform() — return same-shape result, useful in groupby
# ---------------------------------------------------------------------------

# Z-score normalize within each group
df["z_score"] = df.groupby("grade")["score"].transform(
    lambda x: (x - x.mean()) / x.std()
)

# Fill missing values with group mean
df["bonus_filled"] = df.groupby("grade")["bonus"].transform(
    lambda x: x.fillna(x.mean())
)

# Multiple transforms at once
transforms = df.groupby("grade")["score"].transform(["mean", "std", "count"])
print(transforms)

# ---------------------------------------------------------------------------
# Rolling windows
# ---------------------------------------------------------------------------

# Time series example
ts = pd.Series(
    [100, 102, 101, 105, 110, 108, 107, 115, 120, 118],
    index=pd.date_range("2025-01-01", periods=10, freq="D"),
)

# Rolling mean (3-day window)
ts_rolling = ts.rolling(window=3).mean()
print(pd.DataFrame({"original": ts, "rolling_mean": ts_rolling}))

# Rolling with custom function
ts_rolling_custom = ts.rolling(3).apply(lambda x: x.max() - x.min())

# Expanding window (cumulative)
ts_expanding = ts.expanding().mean()

# Exponential weighted moving average
ts_ewm = ts.ewm(span=3).mean()

# ---------------------------------------------------------------------------
# Vectorized operations vs loops — performance comparison
# ---------------------------------------------------------------------------

n = 1_000_000
data = pd.Series(np.random.randn(n))

# ❌ Slow: Python loop
# result = [x * 2 for x in data]  # ~0.5-1 second

# ✅ Fast: vectorized operation
result = data * 2  # ~10-20x faster

# ❌ Slow: .apply() with custom function
# result = data.apply(lambda x: x**2 + 2*x + 1)

# ✅ Fast: vectorized
result = data**2 + 2 * data + 1

# Conditionals: use np.where() instead of .apply()
df["status"] = np.where(df["score"] >= 90, "Honors", "Regular")

# Multiple conditions: use np.select()
conditions = [
    df["score"] >= 90,
    df["score"] >= 80,
    df["score"] >= 70,
]
choices = ["A", "B", "C"]
df["letter_grade"] = np.select(conditions, choices, default="D")

# ---------------------------------------------------------------------------
# When .apply() is actually appropriate
# ---------------------------------------------------------------------------

# Complex row-wise logic that can't be vectorized
def complex_logic(row):
    if row["grade"] == "A" and row["score"] > 90:
        return row["score"] * 1.2
    elif row["grade"] == "B":
        return row["score"] * 1.05
    return row["score"]

df["adjusted"] = df.apply(complex_logic, axis=1)
```