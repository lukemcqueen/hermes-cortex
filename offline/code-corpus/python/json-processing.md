---
language: python
tags: [io, string]
title: JSON Processing
description: Loading, saving, filtering, and transforming JSON data.
source: pattern
---

```python
import json

def flatten_json(data, parent_key='', sep='.'):
    """Flatten nested JSON to dot-notation keys."""
    items = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_key = f'{parent_key}{sep}{k}' if parent_key else k
            if isinstance(v, (dict, list)):
                items.extend(flatten_json(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            new_key = f'{parent_key}[{i}]'
            if isinstance(v, (dict, list)):
                items.extend(flatten_json(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
    return dict(items)

def filter_json(data, predicate):
    """Recursively filter dicts/lists where predicate(key, value) is True."""
    if isinstance(data, dict):
        return {k: filter_json(v, predicate) for k, v in data.items()
                if predicate(k, v) and filter_json(v, predicate)}
    if isinstance(data, list):
        return [filter_json(item, predicate) for item in data
                if filter_json(item, predicate)]
    return data

def pretty_print(data, sort_keys=True):
    return json.dumps(data, indent=2, sort_keys=sort_keys, ensure_ascii=False)
```
