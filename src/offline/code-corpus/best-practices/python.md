---
language: python
tags: [python, best-practices, style, idiomatic]
title: Python Best Practices
description: PEP 8, type hints, list comprehensions, context managers, dataclasses, pathlib over os.path, and f-strings
source: pattern
---

# Python Best Practices

## PEP 8 — Style
- 4 spaces per indentation level, no tabs
- Maximum line length of 79 characters (99 for long strings)
- Imports: standard lib → third-party → local, separated by blank lines
- Use `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_CASE` for constants

## Type Hints
Always annotate function signatures:

```python
from typing import Sequence, Optional


def calculate_mean(values: Sequence[float]) -> Optional[float]:
    """Return the arithmetic mean, or None if the sequence is empty."""
    if not values:
        return None
    return sum(values) / len(values)
```

## List Comprehensions & Generator Expressions
Prefer comprehensions over `map`/`filter` with lambdas:

```python
# Idiomatic
squares = [x**2 for x in range(20) if x % 2 == 0]

# Use generator for large sequences
total = sum(x**2 for x in range(10_000_000))
```

## Context Managers
Use `with` statements for resource cleanup — files, locks, database connections:

```python
from pathlib import Path

path = Path("data.txt")
with path.open(encoding="utf-8") as f:
    content = f.read()
```

## Dataclasses
Prefer `dataclasses` over manual `__init__`/`__repr__`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5
```

## pathlib over os.path
`pathlib` is cross-platform and composable:

```python
from pathlib import Path

data_dir = Path.home() / "data" / "raw"
data_dir.mkdir(parents=True, exist_ok=True)

# Instead of: os.path.join(os.path.expanduser("~"), "data", "raw")
```

## f-strings
Always use f-strings for string formatting:

```python
name, score = "Alice", 42
print(f"Player {name!r} scored {score:.2f} points")
# Prefer over %, .format(), or string concatenation
```

## Additional Patterns
- Prefer `is` / `is not` for `None` checks (`x is not None`)
- Use `_` for unused loop variables
- Use `@classmethod` for alternative constructors
- Leverage `Enum` over magic strings/constants