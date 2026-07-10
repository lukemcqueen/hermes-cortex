# Python Test Env Var Pitfalls

## Module-Level Constants from Env Vars

Many Python services define config at module load time:

```python
MEILISEARCH_URL = os.getenv("MEILISEARCH_URL", "")
MEILISEARCH_API_KEY = os.getenv("MEILISEARCH_API_KEY", "")
```

These are resolved ONCE at import time and become module-level constants.
If the project's `./run` script sources `.env` before launching pytest,
these constants get populated with real env values — even in test.

## The Trap

Patching only the constants you think the assertion checks:

```python
# BUG: patches URL but not API_KEY
with patch("services.search_index.MEILISEARCH_URL", "http://localhost:7700"):
    result = index_works(works)
    mock_client.assert_called_once_with("http://localhost:7700", "")  # FAILS
```

`_get_client()` uses BOTH `MEILISEARCH_URL` AND `MEILISEARCH_API_KEY`.
The API_KEY constant still holds the real value from `.env`.

## The Fix

Patch ALL module-level constants that affect the code path under test,
not just the one you're asserting on:

```python
with (
    patch("services.search_index.MEILISEARCH_URL", "http://localhost:7700"),
    patch("services.search_index.MEILISEARCH_API_KEY", ""),
):
    result = index_works(works)
    mock_client.assert_called_once_with("http://localhost:7700", "")
```

## Root Cause

When `./run` sources `.env` with `set -a` + `source`, env vars are exported
into the shell environment. Pytest inherits them. Module-level `os.getenv()`
calls at import time pick them up before any test code runs.

## Detection

Run the failing test with a debug print or look at the error message —
the `Actual:` line in the assertion error reveals the real value:

```
Expected: Client('http://localhost:7700', '')
  Actual: Client('http://localhost:7700', 'acme-master-key')
                                ^^^^^^^^^^^^^^^^^^^ this is from .env
```

## Prevention

- In tests that patch module-level config constants, always check the
  function/code path to identify ALL constants it uses.
- Use `contextlib.ExitStack` or nested `with` blocks to patch multiple
  constants as a group.
- If the project has many such constants, consider a conftest fixture
  that zeros them out before every test class.
