---
name: hermetic-python-testing
description: "Write Python modules with hermetic unit-test seams."
version: 1.0.0
category: software-development
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [testing, python, isolation, hermetic, unit-test, seams]
    related_skills: [test-driven-development, codebase-design, survey-before-action]
---

# Hermetic Python Testing

Write Python modules so their unit tests never touch real state, real
credentials, or real network — and prove it. Born from telegram_notify S2
(2026-08-08): tests silently wrote to `~/.hermes-cortex/state/` and read the
real `~/.hermes/.env` until the module was restructured.

## When to Use

- Writing a new Python module that reads env vars, paths, or config files
- Adding L0 unit tests to a module that touches files, state, or network
- A test "passes" but you suspect it hit real resources (check the module's
  log/state files for unexpected entries)
- Refactoring a module to be testable without mocking the whole world

## Core Rules

### 1. Resolve paths LAZILY, never at import time

```python
# ❌ BAD — frozen at import; tests setting the env var after import hit REAL paths
STATE_FILE = Path(os.environ.get("MY_STATE_DIR", Path.home() / ".x")) / "state.json"

# ✅ GOOD — resolved per call; tests point it at tmp_path via monkeypatch.setenv
def _state_file() -> Path:
    return Path(os.environ.get("MY_STATE_DIR", Path.home() / ".x")) / "state.json"
```

Import-time constants freeze the path for the whole process. Tests that set
env vars AFTER import (the standard `monkeypatch.setenv` pattern) silently
read/write the real location. Symptom to watch for: a module's real log file
or state JSON appears in `~/.hermes-cortex/state/` after a test run.

### 2. Expose seams for clock and send, then monkeypatch them

```python
def _now() -> float: return time.time()
def _sleep(s: float) -> None: time.sleep(s)
def _send_once(token, chat_id, text): ...   # the network boundary
```

Tests patch these module attributes:
```python
with patch.object(tn, "_now", side_effect=fake_now), \
     patch.object(tn, "_send_once", side_effect=fake_send):
    ...
```
This tests coalescing windows, retry budgets, and backoff with a fake clock
and zero network.

### 3. Hermetic fixture setup — state dir AND env file, both in tmp

Every test that exercises the module gets its own tmp state dir and a fake
env file:

```python
def _setup(tmp_path, monkeypatch, chat="111222333", quiet="", mute=""):
    state_dir = tmp_path / "state"; state_dir.mkdir(exist_ok=True)
    env_file = tmp_path / "env"
    env_file.write_text(f"TELEGRAM_BOT_TOKEN=123456:TESTTOKEN\nTELEGRAM_HOME_CHANNEL={chat}\n")
    monkeypatch.setenv("MY_STATE_DIR", str(state_dir))
    monkeypatch.setenv("MY_ENV_FILE", str(env_file))
    return state_dir, env_file
```

### 4. Verify the hermeticity — never trust "tests passed"

After the suite is green, confirm no real resources were touched:
- The module's real state/log/lock files must NOT exist afterward
- No real credentials were read (check for side effects like real sends)
- Grep the test file for real identifiers (chat ids, tokens, hostnames,
  `/home/<user>/` paths) — placeholder values only

## Verification

- `pytest tests/test_<module>_unit.py -q` → all pass
- The module's real state dir is clean after the run (no leftover files)
- `grep -nE "<real-chat-id>|<real-host>|/home/<user>/" tests/` → no hits
- No network calls happened (fake send patched in; check no real HTTP in log)

## Pitfalls

- **NEVER mutate `sys.path` in test files to import the module under test.**
  A `sys.path.insert(0, <repo>/core)` in one suite SHADOWS same-named
  modules/packages for every sibling suite running later in the same pytest
  process. Verified 2026-09-02: inserting `<repo>/core` made
  `import cortex_bus` resolve to the `core/cortex_bus/` PACKAGE instead of
  the `lib/cortex_bus.py` MODULE a sibling suite (test_bus_outbox) expected
  → ImportErrors in the full run, green in isolation. The suite that
  "passes alone but breaks others" is the culprit — run the pair together
  to confirm. Fix for pure-stdlib modules under test: load them by FILE
  PATH with a unique module name, zero path mutation:
  ```python
  def _load(name, path):
      spec = importlib.util.spec_from_file_location(name, os.path.normpath(path))
      assert spec is not None and spec.loader is not None, f"cannot load {path}"
      mod = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(mod)
      return mod
  validate = _load("cortex_bus_validate_test", "core/cortex_bus/validate.py")
  ```
  Works whenever the module has no intra-package imports. If it does, use a
  `conftest.py` `pythonpath` entry (pytest-managed) instead of hand-rolled
  inserts.
- **Import-time path constants** are the #1 hermeticity killer (see rule 1).
- **Real identifiers in fixtures** — a numeric chat id (e.g. `111222333`)
  looks like an arbitrary integer and sails through the secret-leak detector;
  the scanner only flags `/home/<user>/` paths and emails. Use placeholders
  (`111222333`) and grep for the real id before committing.
- **State leakage across tests** — every test needs its OWN tmp state dir;
  sharing one makes tests order-dependent.
- **The module's own `if __name__ == "__main__"` self-test** should also go
  through the same seams, or it will hit real resources when run manually.
