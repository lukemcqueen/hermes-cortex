---
name: hermetic-python-testing
description: "Write Python modules with hermetic unit-test seams. Covers sandboxed inputs AND live-side-effect output defaults (telegram/webhook/mail routes)."
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

### 5. Override live-side-effect defaults EXPLICITLY — sandboxed inputs are not hermeticity

A test that feeds tmp_path INPUTS can still act on the real world if the tool
under test has a default OUTPUT route. Proven 2026-09-30: the bridge-runner
test ran `cortex-bus-bridge-run.py` on a tmp echo.py without `--deliver` — the
runner's default is Telegram, so every test run sent `cron:test-echo / hello
from test` to the user's real chat (repeated complaints: "I keep seeing
this"). Before invoking any tool/CLI in a test, grep its args/env for defaults
that route to a real channel (messenger, webhook, mail, metrics) and pass the
explicit safe target (`--deliver local`, `CORTEX_DEPLOY_HOME=tmp_path`).
Assert the live default in a dedicated test — never exercise it by accident.

### 6. An imported module must not mutate `os.environ` at import

Loading a module is not a side-effect-free act. A module that parses an env
file into `os.environ` at MODULE scope poisons the whole pytest process for
every suite that runs after it. Verified 2026-10-01: a deploy script
exported the canonical env file at import; a metrics suite `exec_module`d it,
so a var added to that file that day leaked into the process env and the
notify suite — which resolves its chat id from `os.environ` FIRST — used the
real value and failed only in the full run.

Two rules follow:

- **The module:** keep env-file parsing in a function called from `main()`
  (`_source_env_overrides()`), never at module scope. Prove it: `exec_module`
  the file and assert no var appeared.
- **The test:** if the code under test reads a process-env var BEFORE its
  fixture file, `monkeypatch.delenv` that var in the fixture. A fixture that
  only points its own env file cannot defend against a leaked process value.

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
- **Queue mock returns for EVERY caller of a seam, not just the call site you
  are testing.** Before writing the mock, grep the function under test's full
  call tree for uses of the seam — a sibling helper (e.g. a probe that queries
  the same LLM/API function) silently consumes the queued responses, and the
  code under test receives the wrong fixture or runs dry. The failure looks
  like a parsing bug in the function under test; the real bug is the mock
  budget. Count the seam's call sites first, then size the queue.
- **Import repo packages at MODULE level in the test file, not inside test
  functions.** A `from pkg.sub import X` written inside a test function
  re-reads `sys.path` at call time; when a sibling suite (or a conftest
  fixture) restores/snapshots `sys.path` between tests, the function-level
  import fails with `ModuleNotFoundError` even though the suite passes in
  isolation. Symptom: green alone, `No module named 'pkg.sub'` only in the
  full run. Import the package at module top (after any `sys.path.insert`) so
  it is cached in `sys.modules` — the cached module resolves from memory and
  is immune to path resets. This is the complement of the shadowing rule
  above: that rule is "your insert breaks siblings"; this is "siblings'
  restore breaks you."
- **Keep fixtures free of long digit runs.** The repo PII guard
  pattern-matches digit sequences as phone numbers and REFUSES the write — a
  10-digit unix timestamp (`1700000000`) and an all-zeros UUID both tripped
  it as "phone number". Use small ints for ids/timestamps (chat id `7`,
  `ts=1`), hex-letter UUIDs (`aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee`), and
  `example.com` for URLs in shared-surface test files. (The flip side of the
  numeric-chat-id rule above: that one is the detector missing a real id;
  this one is the detector flagging a fake one.)
- **A package module that imports cleanly can still crash when run as a
  script.** Relative imports (`from .transport import X`) need a parent
  package, so `python3 daemon.py` / systemd `ExecStart` fails with
  "attempted relative import with no known parent package" even though
  `from pkg.daemon import main` works. Verify the REAL invocation path, not
  just the import. Make one file work both ways with the run-as-script
  bootstrap:
  ```python
  if __package__ in (None, ""):
      import sys
      from pathlib import Path
      sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
      __package__ = "<pkg_name>"
  ```
- **Do not replace a monkeypatchable module constant with a hardcoded path.**
  Repointing a reader from `SOME_HOME / ".env"` to a literal
  `Path.home() / "x" / ".env"` silently broke the test that redirects it with
  `monkeypatch.setattr(mod, "SOME_HOME", tmp)` — it read the real host path and
  failed. Keep a module-level constant (e.g. `CORTEX_ENV_FILE`) and let tests
  patch THAT; a hardcoded path has no seam.
- **To find WHICH test pollutes `os.environ`, hook pytest — and run with `-s`.**
  A throwaway plugin (`-p <name>`, module on `PYTHONPATH`) that prints at
  `pytest_runtest_setup` when the leaked var is present, plus the previous test
  id, pinpoints the leaker in one full run. Without `-s` pytest CAPTURES and
  DISCARDS a passing test's output, so the print never appears and you wrongly
  conclude "no leak". Check the var at SETUP, not teardown — fixtures undo
  their own patches during teardown, so a teardown probe misses real leaks.
 - **A flaky test is not evidence the artifact is broken — probe the artifact
 OUT-OF-BAND before "fixing" it.** Identical code that fails 2 runs in 3 is a
 RACE, and the race is often in the TEST. Before touching the module under
 test, drive it directly by hand (same request, outside pytest); if it answers
 correctly, the fault is the harness you wrote, not the code you were about to
 "fix". Re-run the single test 3x first — deterministic vs flaky selects
 completely different fixes, and guessing wrong means rewriting working code.
 - **A stdio server test must READ INCREMENTALLY — closing stdin races the last
 response.** A stdio server exits on stdin EOF, so
 `subprocess.run(cmd, input=init + "\n" + ready + "\n" + request, ...)` can
 kill it before it flushes the final reply; the test then judges a partial
 transcript and blames the server. Use `Popen`, write+flush each message, read
 stdout until the response you need arrives (or a deadline expires), then
 terminate. A real client holds stdin open — the test must not encode a race
 the product does not have.
