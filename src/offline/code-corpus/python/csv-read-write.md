---
language: python
tags: [io, file, util, pattern]
title: CSV Read/Write with DictReader & DictWriter
description: Reading and writing CSV files using the csv module with DictReader, DictWriter, type coercion, and error handling.
source: pattern
---

```python
import csv
import io
from typing import Optional


# ---- Sample data ---- #
HEADER = ["name", "age", "city"]
ROWS = [
    {"name": "Alice", "age": "30", "city": "New York"},
    {"name": "Bob", "age": "25", "city": "London"},
    {"name": "Charlie", "age": "35", "city": "Tokyo"},
]


def write_csv(filepath: str, rows: list[dict], fieldnames: Optional[list[str]] = None) -> None:
    """Write a list of dictionaries to a CSV file."""
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(filepath: str) -> list[dict[str, str]]:
    """Read a CSV file into a list of dictionaries (all values are strings)."""
    with open(filepath, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def coerce_row(row: dict[str, str], types: dict[str, type]) -> dict:
    """Convert selected string fields to requested Python types."""
    coerced = dict(row)
    for col, typ in types.items():
        val = coerced.get(col)
        if val is not None and val != "":
            coerced[col] = typ(val)
    return coerced


# ---- Example usage ---- #
if __name__ == "__main__":
    import tempfile, os

    # Write
    tmp = os.path.join(tempfile.gettempdir(), "example.csv")
    write_csv(tmp, ROWS, fieldnames=HEADER)
    print(f"Wrote {len(ROWS)} rows to {tmp}")

    # Read
    loaded = read_csv(tmp)
    for row in loaded:
        # Coerce age to int
        typed = coerce_row(row, {"age": int})
        print(f"{typed['name']:>8}  {typed['age']:>3}  {typed['city']}")

    # Cleanup
    os.remove(tmp)

```
