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

**Prefer a SUITE-LEVEL kill-switch over per-call flags.** Passing the safe
target into the test you happen to be writing does not protect the suite: the
next test someone adds calls the same function with the same dangerous default,
and the live channel fires again. Put an autouse SESSION fixture in
`conftest.py` that redirects the module's config away from production for the
whole process — point its env-file at a path that does not exist and clear the
destination chat/webhook variable. The fail-safe direction is "no credential →
skip", never "no credential → guess". Tests that genuinely exercise the send
path set their own values back via `monkeypatch`, so the guard costs them
nothing.

**Mocking the write does NOT mock the notify.** A post-commit side effect sits
AFTER the call you patched: a unit test that mocks the DB layer and asserts the
stored value still runs the notification that write triggers. Verified: a test
proving a shell payload is stored as a literal — mocking only the query layer —
also sent a real message on every run, which surfaced as recurring user noise
("I keep seeing this") that could never resolve because each run minted a fresh
id. When you mock a dependency, read the function you are calling through to the
END and list every external effect that follows the mocked call.

**A guard needs a control proving the GUARD did the work.** "notify returned
False" also passes if the module is simply broken. Pair it: assert the send path
refuses under the suite's environment, AND assert that with a valid env file the
same probe DOES resolve its credential (a read-only call — no send). Without the
second half, the first half proves nothing.

**A tool you invoke may detect its SUBJECT on the inherited PATH.** When the
code under test shells out and probes for a binary (`command -v <tool>`), passing
the ambient `PATH` through means the case asserting "tool not installed" can be
satisfied by the runner's own install: the audited host is no longer the only
source of truth, the assertion flips per machine, and the failure names nothing
useful ("expected exit 1, got 0"). Scrub the PATH for every case — drop each
directory that actually contains the binary — and put the detected route in the
failure DETAIL (`tool_on_PATH=<which(...)>`, `home_tool=<exists>`), so the next
red run says which route the tool took instead of only the exit code.

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

### 7. An imported module's LOGGER writes to real state

Loading a module runs its module-level logging setup. A module that attaches a file
handler at import (a `RotatingFileHandler` over a real log directory) means every
test that imports it APPENDS to that production log, and the entries are
indistinguishable from real ones — a fabricated cycle number or a `(test)` error line
lands in the audit trail a reviewer will later read as history. Same family as rule 6:
import is not a side-effect-free act.

- **Silence by LEVEL, and leave the handler attached.** Setting the logger above
  CRITICAL suppresses records. Clearing handlers is stronger but destroys the seam you
  need to prove the silencing works, and a module that re-attaches handlers later
  defeats the clear.
- **Prove the "it did not write" assertion is not vacuous.** An assertion that a real
  file did not grow also passes when the code could never have written to it — e.g.
  the module resolves its log path from a constant the test redirected. Check both
  directions, and make the control write NOTHING (writing to prove a file is not
  written to is self-defeating): first assert the logger carries a handler BOUND to
  the real target (a `FileHandler`'s `baseFilename`), then detach it, restore the
  level with a counting handler attached, and assert records ARE emitted — so there
  was something to suppress — then re-attach and assert the silenced run contributes no
  FABRICATED line. If the control cannot emit, the test is measuring nothing.
- **Assert the "did not write" property by CONTENT, never by file SIZE.** A byte-equality
  check on a shared log is racy: any concurrent writer — a cron, a deploy, another
  agent — appending a legitimate entry during the measurement window fails a test about
  YOUR code, i.e. a false report of the very thing the test claims to measure. Read the
  bytes appended in the window and assert none of them carries the test's own markers
  (its fabricated ids, its session name, its `(test)` strings); if something else wrote
  meanwhile, report that as non-test growth instead of failing on it.
- **Know what the module binds at IMPORT vs what you patch afterwards.** A handler
  built at import keeps the real path even after the test patches the module's HOME; a
  path resolved per call follows the patch. Assert what is actually bound before
  trusting either result — a passing one-way size check is a claim about your probe,
  not about the artifact.

### 8. Once-only initialization must be keyed to the RESOURCE, not to the process

A module-level "already done" flag (`_SCHEMA_DONE = False`) makes the FIRST
resource a process touches the only one that ever gets set up. Any caller that
switches resources later — a test repointing the module constant at a tmp file,
a tool opening a second database — receives an un-set-up resource and fails on
the first query against it (`no such table: <name>`). The failure reads as
flakiness: those tests pass in isolation and fail in a full run, because some
other test has already opened the first resource.

- **Key the guard to the thing that varies** — the database FILE, the directory
  being prepared, the fixture identity — a SET of resources rather than a
  boolean.
- **Read the key from the connection/handle under test, not from the module
  constant.** The caller may have repointed the constant after the connection was
  opened, and the question the guard actually answers is "does THIS resource have
  its setup" (`PRAGMA database_list` gives the file a sqlite connection is
  attached to).
- **This is a SEAM, not just a test fix.** The process-global flag is untestable
  by construction: no fixture can prove setup happened for the second resource
  while the code can only ever answer for the first. Fix the module, then pin it
  with a test that opens two resources in one process — and a premise test so the
  guard cannot pass vacuously if the DDL entry point moves.
- **When the repo's own suite is red, test the claim that it is not your fault.**
  Re-run the full suite with no lock and no in-flight change and compare the
  failure LIST, not the count: identical list = pre-existing, and "passes in
  isolation, fails in the full run" points at module state, not at you.

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
 "fixing" it. Re-run the single test 3x first — deterministic vs flaky selects
 completely different fixes, and guessing wrong means rewriting working code.
 **If the flake stops reproducing, STOP bisecting and bank what you proved.** A
 failure that vanishes after N runs was a WINDOW, not an ordering: further
 bisect rounds buy nothing and cost the session. Record the MECHANISM you
 demonstrated with a control (a stub that reproduces it on demand), make the
 test hermetic against that mechanism, and leave the discriminator in the
 failure detail so a recurrence names its own route. "Mechanism proven, trigger
 unidentified, guarded and diagnosed" is a complete result — report it that way
 instead of widening the search.
- **Asserting on SOURCE TEXT? Strip comments and docstrings first — the file
  legitimately names the thing you are asserting is absent.** A guard written as
  `assert "addSystemPrompt" not in src` failed against correct code, because the
  file's own comment explained *why there is no `addSystemPrompt()`*. Grep the
  raw text and you flag your own documentation; strip comment lines (and
  preferably match the CALL, `addSystemPrompt(`, not the bare word) before
  asserting. Same family as any probe that is wrong rather than the code:
  a failing assertion is a claim about your probe first and the artifact
  second.
- **A guard that asserts a DETECTOR must assert the real one, not a plausible
  one.** `assert "sys.platform" in src` failed against a store that correctly
  detects macOS via `os.uname().sysname == "Darwin"`. Read the implementation
  and assert what it actually does — or better, make the test
  BEHAVIOURAL: force the branch (set the flag) and assert the built command,
  instead of grepping for a string that merely resembles the mechanism.
- **Whitespace-normalise before asserting a PHRASE against source text.** The
  same family as the rule above: asserting a multi-word phrase failed because
  the prose wrapped across a line break, so the substring never appeared
  contiguously. Assert against `" ".join(text.split())`, or drop the phrase
  assertion for a structural one.
- **Test the code you CHANGED — a neighbouring green suite is not evidence.**
  Reporting "24 passed" from a test file that never imports either modified
  module verifies nothing about the change; it is reassurance shaped like
  proof, and it is the finding a reviewer will (correctly) raise. Before citing
  a test run as evidence, check the path: does any test in that file FAIL if you
  revert the change? If not, write one that does — a behavioural test on the
  changed code path, not a broader suite that happens to be nearby.
- **A fallback/shim only defined when a dependency is ABSENT cannot be tested
  from the machine that has the dependency.** A guard asserting on the
  conditional-shim class passed everywhere it was run and tested nothing: on a
  host with the real package installed, the shim is never defined, so the
  assertion inspected the real library instead. Drive the absent case for real
  in a subprocess, by making the import fail:
  ```python
  # a None entry in sys.modules makes `import pkg` raise ImportError
  script = "import sys; sys.modules['pkg'] = None; sys.modules['pkg.sub'] = None\n"
  script += "...load the module by path, assert the fallback engaged..."
  subprocess.run([sys.executable, "-c", script], ...)
  ```
  A custom `find_spec` that RAISES ImportError is the wrong tool: the import
  machinery does not catch it, so it aborts instead of falling through to your
  guard. This case is worth a real test because it is the whole point of the
  fallback — and it is exactly where a pre-existing hard exit or an
  unreachable guard hides.
- **A test that reads AMBIENT state tests the machine, not the code.** A refusal
  case passed for as long as an unrelated stale lock file happened to exist in the
  host's state dir, and went red the moment it was cleared — it had never once
  exercised the branch it claimed to cover. Anything a test reads from a shared
  location (locks, journals, session markers, live DB rows, **and inherited
  environment variables**) is an accidental fixture: point it at a temp
  `HOME`/`ROOT`, inject the value, or `monkeypatch.delenv(<VAR>, raising=False)` in
  the shared runner when the test asserts the VAR-ABSENT branch. An agent shell
  commonly exports identity vars (`AGENT_NAME`) — a test that passes `--agent`
  explicitly still silently depends on the caller NOT exporting one, so it goes
  green in a bare CI shell and red on a real host. Keep the real-resource assertion
  as ONE explicitly-labelled case. Clearing unrelated state is the cheapest way to
  discover tests that were passing by accident.
- **A test that repoints a SHARED module attribute (a module it does not own)
  must restore it in `finally`.** `setattr(doctor_checks, "HOME", tmp)` looks
  like ordinary fixture setup and is not: the value outlives the test, survives
  into every later file in the process, and points at a temporary directory the
  harness then deletes. Every later test that reads that module silently
  produces nothing. The signature is worth memorising: **the failures appear in a
  DIFFERENT file from the culprit, and the culprit's own tests are green** — so
  the file you are staring at is the symptom, not the cause. Restore on the way
  out whether the body succeeded or raised, and add a regression test in the
  mutating file asserting the attribute is unchanged after the call.
- **Finding WHICH test pollutes shared state is a pairing search, not a reading
  exercise.** See `references/order-dependent-failure-bisect.md` for the recipe
  — run the victim alone, pair it with each candidate that touches the module,
  then bisect the failing group — and for what to do when the failure will not
  reproduce at all.
