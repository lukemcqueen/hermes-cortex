---
language: python
tags: [config, sys, util, pattern]
title: Environment Variables
description: Reading and managing environment variables with os.environ, os.getenv, python-dotenv, type coercion, and safe defaults.
source: pattern
---

```python
import os
import sys
from typing import Optional, TypeVar

T = TypeVar("T")


# ---- Core helpers ---- #
def get_str(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read a string env var, returning default if absent."""
    return os.environ.get(key, default)


def get_int(key: str, default: Optional[int] = None) -> Optional[int]:
    """Read an integer env var, returning default on missing or invalid."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_bool(key: str, default: bool = False) -> bool:
    """Parse a boolean env var (true/1/yes/y => True, everything else => False)."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes", "y")


# ---- Load .env file (if python-dotenv is available) ---- #
def load_dotenv(path: Optional[str] = None) -> None:
    """Load a .env file into os.environ. Falls back to '.env' if path is None."""
    try:
        from dotenv import load_dotenv as _load
        loaded = _load(path) if path else _load()
        if loaded:
            print(f"Loaded environment from {path or '.env'}")
    except ImportError:
        print("python-dotenv not installed; skipping .env loading", file=sys.stderr)


# ---- App config sourced from environment ---- #
class AppConfig:
    def __init__(self) -> None:
        self.host: str = get_str("APP_HOST", "0.0.0.0")  # type: ignore[assignment]
        self.port: int = get_int("APP_PORT", 8000) or 8000
        self.debug: bool = get_bool("APP_DEBUG", False)
        self.database_url: str = os.environ.get(
            "DATABASE_URL",
            "sqlite:///app.db",
        )
        self.secret_key: str = os.environ["SECRET_KEY"]  # will raise KeyError if missing

    def __repr__(self) -> str:
        return (
            f"AppConfig(host={self.host!r}, port={self.port}, "
            f"debug={self.debug}, db={self.database_url!r})"
        )


# ---- Example ---- #
if __name__ == "__main__":
    # Optionally load a .env file
    load_dotenv()

    # Basic usage
    print(f"HOME = {get_str('HOME')}")
    print(f"WORKERS = {get_int('WORKERS', 4)}")
    print(f"ENABLE_CACHE = {get_bool('ENABLE_CACHE', True)}")

    # Structured config -- requires SECRET_KEY to be set
    try:
        cfg = AppConfig()
        print(cfg)
    except KeyError as e:
        print(f"Missing required env var: {e}")
        sys.exit(1)

```
