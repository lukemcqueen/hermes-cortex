---
language: python
tags: [errors, debugging, python, troubleshooting]
title: Common Python Errors
description: Frequent Python errors — ModuleNotFoundError, ImportError, asyncio event loop closed, pip dependency conflicts, ValueError, KeyError — with messages, causes, and fixes
source: pattern
---

```python
# ---------------------------------------------------------------------------
# 1. ModuleNotFoundError / ImportError
# ---------------------------------------------------------------------------
# Error message:
#   ModuleNotFoundError: No module named 'requests'
#   ImportError: cannot import name 'xxx' from partially initialized module 'yyy'
#
# Cause:
#   - Package not installed: pip install missing
#   - Circular imports: module A imports B, B imports A (before A finishes loading)
#   - Name mismatch: typo in import statement or renamed function
#   - Virtual environment not activated: running system Python, not venv Python
#
# Fixes:

# Fix 1: Install the missing package
# pip install requests

# Fix 2: Check your virtual environment
# which python       # Should point to your venv
# pip list | grep requests

# Fix 3: Fix circular imports — restructure or use lazy imports
# Module A:
#   def foo():
#       from module_b import bar   # Lazy import inside function
#       bar()

# Fix 4: Check for name shadowing — don't name your script the same as a library
# ❌ Don't: requests.py (shadows the requests library)

# ---------------------------------------------------------------------------
# 2. RuntimeError: Event loop is closed (asyncio)
# ---------------------------------------------------------------------------
# Error message:
#   RuntimeError: Event loop is closed
#   RuntimeError: Cannot close a running event loop
#
# Cause:
#   - Running asyncio code in a Jupyter notebook or REPL where loop is already running
#   - Closing the loop manually or using deprecated asyncio.get_event_loop()
#   - Using asyncio.run() inside a running event loop
#
# Fixes:

# Fix 1: Use nest_asyncio (in Jupyter/REPL)
# pip install nest_asyncio
import nest_asyncio
nest_asyncio.apply()

# Fix 2: Use asyncio.run() at the top level only, never inside an async function
async def main():
    await asyncio.sleep(1)
    print("Done")

# ✅ Correct
asyncio.run(main())

# ❌ Wrong — calling asyncio.run inside an async function
# async def outer():
#     asyncio.run(main())  # RuntimeError!

# Fix 3: Reuse the existing loop
import asyncio
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# ---------------------------------------------------------------------------
# 3. pip dependency conflicts
# ---------------------------------------------------------------------------
# Error message:
#   pip._vendor.resolvelib.resolvers.ResolutionImpossible:
#     The conflict is caused by: package-a 2.0 depends on pkg-b>=2.0
#     package-b 1.5 depends on pkg-b<2.0
#   ERROR: Cannot install -r requirements.txt
#
# Cause:
#   - Two packages require incompatible versions of the same dependency
#   - pip's new resolver (2020+) is stricter about conflicts
#
# Fixes:

# Fix 1: Let pip find a compatible set
# pip install -r requirements.txt --upgrade

# Fix 2: Use pip-tools to compile a compatible requirement set
# pip install pip-tools
# echo "requests" > requirements.in
# echo "urllib3<2" >> requirements.in
# pip-compile requirements.in  # produces requirements.txt

# Fix 3: Create a fresh virtual environment
# python -m venv .venv
# source .venv/bin/activate
# pip install -r requirements.txt

# Fix 4: Use `--use-deprecated legacy-resolver` (temporary workaround)
# pip install package-a package-b --use-deprecated legacy-resolver

# Fix 5: Pin exact versions that are known to work
# In requirements.txt:
# pkg-b==1.5.0
# package-a==1.0.0

# ---------------------------------------------------------------------------
# 4. ValueError
# ---------------------------------------------------------------------------
# Error messages:
#   ValueError: invalid literal for int() with base 10: 'abc'
#   ValueError: cannot convert float NaN to integer
#   ValueError: The truth value of a DataFrame is ambiguous
#
# Cause:
#   - Converting a non-numeric string to int/float
#   - NaN in a column being converted to int
#   - Using `if df:` or `if series:` instead of `.any()` or `.all()`
#
# Fixes:

# Fix 1: Handle invalid input gracefully
try:
    value = int(user_input)
except ValueError:
    value = 0  # or None, or log + retry

# Fix 2: Handle NaN before converting
import pandas as pd
import numpy as np

df = pd.DataFrame({"val": [1.0, 2.5, np.nan, 4.0]})
# ❌ ValueError: df["val"].astype(int)
# ✅ Fix: fill NaN then convert
df["val"] = df["val"].fillna(0).astype(int)

# Fix 3: Use pd.to_numeric with errors='coerce'
df["col"] = pd.to_numeric(df["col"], errors="coerce")

# Fix 4: Correct DataFrame truthiness check
# ❌ if df:
# ✅ if not df.empty:
# ✅ if len(df) > 0:
# ✅ if df["score"].any() > 0:

# ---------------------------------------------------------------------------
# 5. KeyError
# ---------------------------------------------------------------------------
# Error message:
#   KeyError: 'column_name'
#   KeyError: 'missing_key'
#
# Cause:
#   - Accessing a dictionary key that doesn't exist
#   - Accessing a DataFrame column that doesn't exist
#   - Typo in column name (case-sensitive!)
#
# Fixes:

# Fix 1: Use .get() for safe key access
data = {"name": "Alice", "age": 30}
# ❌ data["missing"]  → KeyError
# ✅ Safe:
print(data.get("missing", "default_value"))

# Fix 2: Check before accessing
if "missing" in data:
    print(data["missing"])

# Fix 3: For DataFrames, use .get() as well
df = pd.DataFrame({"name": ["Alice"]})
# ❌ df["names"]  → KeyError
# ✅
if "names" in df.columns:
    print(df["names"])
else:
    print("Column not found")

# Fix 4: Use .reindex() to handle missing columns consistently
expected_cols = ["name", "age", "city"]
df = pd.DataFrame({"name": ["Alice"], "age": [30]})
df = df.reindex(columns=expected_cols, fill_value="N/A")
print(df)
#    name  age city
# 0  Alice   30  N/A

# ---------------------------------------------------------------------------
# 6. TypeError: 'NoneType' object is not subscriptable / callable
# ---------------------------------------------------------------------------
# Error message:
#   TypeError: 'NoneType' object is not subscriptable
#   TypeError: 'NoneType' object is not callable
#
# Cause:
#   - A function returned None when you expected a value (e.g., dict/string)
#   - Overwriting a variable name: list = [1,2,3] then calling list([4,5])
#   - Chained operations where an intermediate step returns None
#
# Fixes:

# ❌ This returns None because .sort() sorts in-place
# result = my_list.sort()
# print(result[0])  # TypeError!

# ✅ Use sorted() instead
result = sorted(my_list)
print(result[0])

# ❌ Don't shadow built-in names
# list = [1, 2, 3]  # Now list() is broken

# ✅ Use different variable names
my_list = [1, 2, 3]

# Fix for chained operations — check each step
def get_data():
    return {"items": [1, 2, 3]}

result = get_data()
if result is not None:
    items = result.get("items", [])
    print(items)
```