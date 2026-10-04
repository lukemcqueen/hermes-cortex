# Task-queue remediation — acceptance evidence

Regenerate with: `bash ops/scripts/manage/run-task-queue-evidence.sh`

Every number below is RE-DERIVED from the live store and the live repo by
running this script. Aggregates only — no row identifiers, so the checks
keep holding for rows added later.

Provenance: a regression test regenerates this report and compares it to
the committed file, so a hand-written table cannot pass for script output.

| Check | Result | Detail |
|---|---|---|
| No pending slice is assigned-and-unstarted | PASS | 0 stranded (baseline 6) |
| Pending-slice pool fully accounted for by its two views | PASS | claimable 16 + assigned 0 = 16 |
| The pool GREW by exactly the released slices (work is reachable again) | PASS | claimable 16 (baseline 9 + 6 released) |
| No row is left parked in `waiting` | PASS | 0 still waiting (baseline 6) |
| Parked rows can return to the claim pool | PASS | waiting->pending=t blocked->pending=t paused->pending=t |
| Every task migration is registered for deploy | PASS | 12 migrations; unregistered: none |
| Every task migration is on the deployed tree | PASS | 12 of 12 deployed |
| DB schema version matches the newest repo migration | PASS | DB=12 repo=12 |
| test_hc_harness failures reproduce WITHOUT this change (pre-existing) | PASS | with changes: ========================= 3 failed, 6 passed in 1.77s ========================== · HEAD~1 worktree: ========================= 3 failed, 6 passed in 1.78s ========================== |

**Verdict: PASS**

## Raw test output — `tests/test_hc_harness.py`

This change does not touch `hc` or its harness registry. The failures below
are reproduced on a HEAD~1 worktree, i.e. WITHOUT this change applied.

### With this change applied

```
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/esther/hermes-cortex
configfile: pytest.ini
plugins: anyio-4.12.1
collected 9 items

tests/test_hc_harness.py F...F...F                                       [100%]

=================================== FAILURES ===================================
________________________ test_lists_registry_harnesses _________________________
tests/test_hc_harness.py:47: in test_lists_registry_harnesses
    assert "cli-extension" in out and "mcp" in out
E   assert ('cli-extension' in "Declared harnesses: 5\n\n  HARNESS          LAYER          STATUS      SURFACE\n  hermes           mcp            shi...all <name> [--dir DIR]   wire it into a project\n  hc harness verify  [<name>]             prove it, don't assume it\n")
________ test_run_line_is_derived_not_the_hand_written_registry_literal ________
tests/test_hc_harness.py:99: in test_run_line_is_derived_not_the_hand_written_registry_literal
    assert printed_tools == expected | {"read", "bash", "edit", "write"}
E   AssertionError: assert {'bash', 'edi..._search', ...} == {'bash', 'edi...ead', 'write'}
E     
E     Extra items in the left set:
E     'mem_search'
E     'session_note'
E     'mem_profile'
E     'session_list'
E     'session_close'...
E     
E     ...Full output truncated (8 lines hidden), use '-vv' to show
____________________ test_hc_entrypoint_dispatches_harness _____________________
tests/test_hc_harness.py:127: in test_hc_entrypoint_dispatches_harness
    assert "pi" in r.stdout and "cli-extension" in r.stdout
E   assert ('pi' in "Declared harnesses: 5\n\n  HARNESS          LAYER          STATUS      SURFACE\n  hermes           mcp            shi...all <name> [--dir DIR]   wire it into a project\n  hc harness verify  [<name>]             prove it, don't assume it\n" and 'cli-extension' in "Declared harnesses: 5\n\n  HARNESS          LAYER          STATUS      SURFACE\n  hermes           mcp            shi...all <name> [--dir DIR]   wire it into a project\n  hc harness verify  [<name>]             prove it, don't assume it\n")
E    +  where "Declared harnesses: 5\n\n  HARNESS          LAYER          STATUS      SURFACE\n  hermes           mcp            shi...all <name> [--dir DIR]   wire it into a project\n  hc harness verify  [<name>]             prove it, don't assume it\n" = CompletedProcess(args=['/home/esther/.hermes/hermes-agent/venv/bin/python3', '/home/esther/hermes-cortex/ops/scripts/h...-dir DIR]   wire it into a project\n  hc harness verify  [<name>]             prove it, don\'t assume it\n', stderr='').stdout
E    +  and   "Declared harnesses: 5\n\n  HARNESS          LAYER          STATUS      SURFACE\n  hermes           mcp            shi...all <name> [--dir DIR]   wire it into a project\n  hc harness verify  [<name>]             prove it, don't assume it\n" = CompletedProcess(args=['/home/esther/.hermes/hermes-agent/venv/bin/python3', '/home/esther/hermes-cortex/ops/scripts/h...-dir DIR]   wire it into a project\n  hc harness verify  [<name>]             prove it, don\'t assume it\n', stderr='').stdout
=========================== short test summary info ============================
FAILED tests/test_hc_harness.py::test_lists_registry_harnesses - assert ('cli...
FAILED tests/test_hc_harness.py::test_run_line_is_derived_not_the_hand_written_registry_literal
FAILED tests/test_hc_harness.py::test_hc_entrypoint_dispatches_harness - asse...
========================= 3 failed, 6 passed in 1.77s ==========================
```

### On a HEAD~1 worktree (this change absent)

```
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
rootdir: /tmp/tq-evidence-clean-tree
configfile: pytest.ini
plugins: anyio-4.12.1
collected 9 items

tests/test_hc_harness.py F...F...F                                       [100%]

=================================== FAILURES ===================================
________________________ test_lists_registry_harnesses _________________________
tests/test_hc_harness.py:47: in test_lists_registry_harnesses
    assert "cli-extension" in out and "mcp" in out
E   assert ('cli-extension' in "Declared harnesses: 5\n\n  HARNESS          LAYER          STATUS      SURFACE\n  hermes           mcp            shi...all <name> [--dir DIR]   wire it into a project\n  hc harness verify  [<name>]             prove it, don't assume it\n")
________ test_run_line_is_derived_not_the_hand_written_registry_literal ________
tests/test_hc_harness.py:99: in test_run_line_is_derived_not_the_hand_written_registry_literal
    assert printed_tools == expected | {"read", "bash", "edit", "write"}
E   AssertionError: assert {'bash', 'edi..._search', ...} == {'bash', 'edi...ead', 'write'}
E     
E     Extra items in the left set:
E     'mem_search'
E     'session_note'
E     'mem_profile'
E     'session_list'
E     'session_close'...
E     
E     ...Full output truncated (8 lines hidden), use '-vv' to show
____________________ test_hc_entrypoint_dispatches_harness _____________________
tests/test_hc_harness.py:127: in test_hc_entrypoint_dispatches_harness
    assert "pi" in r.stdout and "cli-extension" in r.stdout
E   assert ('pi' in "Declared harnesses: 5\n\n  HARNESS          LAYER          STATUS      SURFACE\n  hermes           mcp            shi...all <name> [--dir DIR]   wire it into a project\n  hc harness verify  [<name>]             prove it, don't assume it\n" and 'cli-extension' in "Declared harnesses: 5\n\n  HARNESS          LAYER          STATUS      SURFACE\n  hermes           mcp            shi...all <name> [--dir DIR]   wire it into a project\n  hc harness verify  [<name>]             prove it, don't assume it\n")
E    +  where "Declared harnesses: 5\n\n  HARNESS          LAYER          STATUS      SURFACE\n  hermes           mcp            shi...all <name> [--dir DIR]   wire it into a project\n  hc harness verify  [<name>]             prove it, don't assume it\n" = CompletedProcess(args=['/home/esther/.hermes/hermes-agent/venv/bin/python3', '/tmp/tq-evidence-clean-tree/ops/scripts/...-dir DIR]   wire it into a project\n  hc harness verify  [<name>]             prove it, don\'t assume it\n', stderr='').stdout
E    +  and   "Declared harnesses: 5\n\n  HARNESS          LAYER          STATUS      SURFACE\n  hermes           mcp            shi...all <name> [--dir DIR]   wire it into a project\n  hc harness verify  [<name>]             prove it, don't assume it\n" = CompletedProcess(args=['/home/esther/.hermes/hermes-agent/venv/bin/python3', '/tmp/tq-evidence-clean-tree/ops/scripts/...-dir DIR]   wire it into a project\n  hc harness verify  [<name>]             prove it, don\'t assume it\n', stderr='').stdout
=========================== short test summary info ============================
FAILED tests/test_hc_harness.py::test_lists_registry_harnesses - assert ('cli...
FAILED tests/test_hc_harness.py::test_run_line_is_derived_not_the_hand_written_registry_literal
FAILED tests/test_hc_harness.py::test_hc_entrypoint_dispatches_harness - asse...
========================= 3 failed, 6 passed in 1.78s ==========================
```
