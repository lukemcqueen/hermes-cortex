# Async Session Factory Lazy Init — Python Module Variable Gotcha

## Problem

When you lazy-init the session factory (to allow `from app.database import Base` without triggering engine creation), the module-level `async_session_factory` starts as `None` and a private `_init_session_factory()` initializes it on first use.

**The gotcha — Python's import binding:**

```python
# database.py
async_session_factory = None

def _init_session_factory():
    global async_session_factory
    if async_session_factory is None:
        async_session_factory = async_sessionmaker(...)
```

```python
# caller.py — BROKEN
from app.database import _init_session_factory, async_session_factory
_init_session_factory()
# async_session_factory is STILL None here
# because `from ... import async_session_factory` created a LOCAL binding
# that points to the old None, not the module's updated value
```

## Fix

**Option A — Return from init (preferred):**

```python
def _init_session_factory():
    global async_session_factory
    if async_session_factory is None:
        async_session_factory = async_sessionmaker(...)
    return async_session_factory

# caller:
factory = _init_session_factory()  # returns the live factory
```

**Option B — Re-import after init:**

```python
from app.database import _init_session_factory
_init_session_factory()
from app.database import async_session_factory  # picks up updated value
```

**Option C — Getter function:**

```python
def get_session_factory():
    _init_session_factory()
    return async_session_factory

# Always safe to call
```

## Prevention

- Use getter functions, not module-level variables, for lazy state
- If a module-level var is unavoidable, document the import-order requirement
- Second `from ... import` after init picks up the update (Python caches modules)
