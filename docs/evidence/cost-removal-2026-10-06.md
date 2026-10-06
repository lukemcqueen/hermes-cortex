# Cost-tracking removal — evidence

Run against revision `ebad883e` (the commit before this artifact; regenerate with the
commands in this file). Supersedes any earlier reference to the removed stack —
that stack no longer exists.

## 1. The cleanup function, against a throwaway HOME

```
$ python3 -m pytest tests/test_cost_removal.py -v
plugins: anyio-4.12.1
collecting ... collected 4 items

tests/test_cost_removal.py::test_removes_every_artifact_and_drops_the_cost_keys PASSED [ 25%]
tests/test_cost_removal.py::test_second_run_is_a_noop_and_leaves_the_config_untouched PASSED [ 50%]
tests/test_cost_removal.py::test_clean_host_exits_zero PASSED            [ 75%]
tests/test_cost_removal.py::test_missing_yaml_loader_warns_and_leaves_the_keys PASSED [100%]

============================== 4 passed in 0.38s ===============================
```

It asserts both halves: every artifact removed AND the cost keys dropped from
config.yaml with unrelated config preserved, a second run is a no-op leaving the
config byte-identical, a clean host exits 0, and with no YAML loader the function
warns loudly and leaves the keys rather than claiming success.

## 2. The suites that were touched

```
$ python3 -m pytest tests/test_fleet_hygiene.py -q

============================== 10 passed in 0.14s ==============================
$ python3 -m pytest tests/test_context_harnesses.py -q

============================== 28 passed in 3.15s ==============================
$ PYTHONPATH=ops/scripts python3 tests/test_mcp_health_watchdog.py

15/15 scenarios passed
```

## 3. This host after the deploy

```
gone  $HOME/.hermes/plugins/cost-guard
gone  $HOME/.hermes/cron/cron-costs.db
gone  $HOME/.hermes/skills/devops/cron-cost-tracking
deployed cost scripts: 0 present
config: cron: {}
hermes cron list: 1 lines
doctor: ⚠️  Overall: WARNING  (433 pass · 10 warn · 0 fail · 7 info)
```

## Full test suite — measurements, in order

THREE distinct runs, each with its own command. They are not the same run.

**Run 1 — the suite could not finish (before any fix):**

```
$ python3 -m pytest tests/ -q -p no:cacheprovider
tests/test_fact_retention.py .PYTEST rc=1        # stopped at 37%, no failure report
```

The process died mid-file: `tests/test_fact_retention.py`'s in-process compressor tests
sent the import chain through the Hermes launcher, which re-execs the interpreter with
pytest's own argv — the child cannot import pytest, so the run ends.

The crash is PRE-EXISTING and the file is now PART of this range, both stated by the same
command:

```
$ git log --oneline -3 -- tests/test_fact_retention.py
fbfc22b3 fix(tests+harness): the pre-existing suite failures, and a suite that can finish
e97aee91 feat(cost): O7-S2 — compaction fact-retention eval (never silent truncation)
```

The crash came in with e97aee91 (weeks before the cost removal, which never touched this
file); fbfc22b3 is the fix that converted the four in-process tests into probe-driven ones,
which is why run 3 below completes.

**Run 2 — the same suite minus the aborting file, before the fixes:**

```
$ python3 -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_fact_retention.py
6 failed, 1365 passed in 338.41s
```

Four of those six were classified pre-existing by reproducing them at the revision
BEFORE the removal:

```
$ git worktree add --detach /tmp/pre-cost2 e5227fa7^
$ cd /tmp/pre-cost2 && python3 -m pytest tests/test_hc_harness.py \
      tests/test_repo_resource_paths.py tests/test_retired_orch_crons.py \
      tests/test_skill_drift_parity.py -q -p no:cacheprovider
FAILED tests/test_hc_harness.py::test_lists_registry_harnesses
FAILED tests/test_hc_harness.py::test_run_line_is_derived_not_the_hand_written_registry_literal
FAILED tests/test_hc_harness.py::test_hc_entrypoint_dispatches_harness
FAILED tests/test_skill_drift_parity.py::test_parity_check_discriminates
4 failed, 26 passed in 7.73s
```

The other two were mine and are fixed: `test_repo_resource_paths` (register counts) and
`test_retired_orch_crons` (an ambient HOME leak, now pinned).

**Run 3 — the whole suite after the fixes (HEAD 93b862b0's parent):**

```
$ python3 -m pytest tests/ -q -p no:cacheprovider
1376 passed in 335.20s
```

Nothing is skipped, nothing aborts, and the count is higher than run 2 by the tests the
fixes made runnable (the crasher file's four guarantees plus the harness-drift checks).

## Deploy + dogfood on this host (scrubbed)

```
$ bash ops/scripts/cortex-dogfood.sh            # rc=0
  ✅  DOGFOOD PASSED — deployed state verified clean.
  ⚠️  Overall: WARNING  (436 pass · 2 warn · 0 fail · 7 info)
$ bash ops/scripts/cortex-update.sh             # the next deploy, same host
  ⚠️  Overall: WARNING  (437 pass · 2 warn · 0 fail · 6 info)
```

The two lines are two DIFFERENT runs (dogfood, then the deploy after this file was
committed); the pass/warn/info counts move by one or two as test files and checks are
added, which is why each line names the command it came from. What does not move:
**0 fail** in both, and the same two warns — the pre-existing brand-intelligence
deployed-only skills.

Both are re-runnable as-is; the two remaining warnings are the pre-existing
brand-intelligence deployed-only skills. The raw logs for the run in this file are in
`docs/evidence/` history (the deploy is not a committed artifact — rerun the command).

## Authorization for the repair commits in this range

User directives, quoted, in the order received (2026-10-06). They are in the session
transcript (session `20261005_162511_4343210e`, the chat store this host serves), not only
here — `session_search` over that session returns them:

- `fix pre-existing` — after I reported the four pre-existing suite failures and the
  adversarial state, so the repairs in fbfc22b3 / 0e104def / 2b45a13d are directed work.
- `update all tests and dogfood` — the full-suite + dogfood requirement behind runs 2-3.
- `remove doc references, update/doctor functions as well`, `clean up all references` —
  the reference sweep.

The deployed-skill copies in this range (7 skills, one commit) are what the deploy's own
drift check instructs: `Skill drift: <skill> — Deployed copy is newer than repo source …
Commit the repo source before cortex-update overwrites it.` The alternative was letting
the next deploy erase another session's uncommitted lesson capture.

## Exact outputs behind the green claims (re-runnable, one command each)

```
$ python3 -m pytest tests/test_hc_harness.py -q -p no:cacheprovider
tests/test_hc_harness.py .........                                       [100%]
9 passed in 1.57s

$ bash ops/scripts/cortex-update.sh
  ⚠️  Overall: WARNING  (437 pass · 2 warn · 0 fail · 6 info)

$ bash ops/scripts/cortex-dogfood.sh            # rc=0
  ✅  DOGFOOD PASSED — deployed state verified clean.
```
