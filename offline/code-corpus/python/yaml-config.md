---
language: python
tags: [config, file, util, io]
title: YAML Config Loading
description: Loading, dumping, and merging YAML configuration with PyYAML: safe_load, dump, multi-document streams, and safe YAML includes.
source: pattern
---

```python
import os
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    print("PyYAML is required. Install: pip install pyyaml")
    sys.exit(1)


def load_config(path: str) -> dict[str, Any]:
    """Load a single YAML document safely."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_multi(path: str) -> list[dict[str, Any]]:
    """Load all YAML documents from a single file (multi-document stream)."""
    with open(path, "r", encoding="utf-8") as f:
        return list(yaml.safe_load_all(f))


def dump_config(data: dict[str, Any], path: str, *, default_flow_style: bool = False) -> None:
    """Write a dictionary as a clean YAML file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=default_flow_style, sort_keys=False)


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge two config dicts (override wins)."""
    merged = dict(base)
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


# ---- Example ---- #
if __name__ == "__main__":
    import tempfile

    cfg1 = load_config(os.path.join(tempfile.gettempdir(), "nonexistent.yml"))
    print("Empty config:", cfg1)

    base = {"database": {"host": "localhost", "port": 5432}, "debug": False}
    override = {"database": {"port": 15432}, "debug": True}
    merged = deep_merge(base, override)
    dump_config(merged, "/tmp/merged_config.yml")
    print("Merged config written to /tmp/merged_config.yml")

```
