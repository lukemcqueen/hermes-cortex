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
pytest's own argv — the child cannot import pytest, so the run ends. That file is
untouched by the removal (`git log -2 -- tests/test_fact_retention.py` ends at e97aee91).

**Run 2 — the same suite minus the aborting file, before the fixes:**

```
$ python3 -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_fact_retention.py
6 failed, 1365 passed in 338.41s
```

Four of those six were reproduced at the pre-change revision in a worktree
(`git worktree add /tmp/pre-cost e5227fa7^` → `4 failed, 26 passed`), which is how they
were classified as pre-existing rather than caused by the removal.

**Run 3 — the whole suite after the fixes (HEAD 93b862b0's parent):**

```
$ python3 -m pytest tests/ -q -p no:cacheprovider
1376 passed in 335.20s
```

Nothing is skipped, nothing aborts, and the count is higher than run 2 by the tests the
fixes made runnable (the crasher file's four guarantees plus the harness-drift checks).

## Deploy + dogfood on this host (scrubbed)

```
$ bash ops/scripts/cortex-update.sh
  ⚠️  Overall: WARNING  (436 pass · 2 warn · 0 fail · 7 info)
$ bash ops/scripts/cortex-dogfood.sh            # rc=0
  ✅  DOGFOOD PASSED — deployed state verified clean.
  ⚠️  Overall: WARNING  (436 pass · 2 warn · 0 fail · 7 info)
```

Both are re-runnable as-is; the two remaining warnings are the pre-existing
brand-intelligence deployed-only skills. The raw logs for the run in this file are in
`docs/evidence/` history (the deploy is not a committed artifact — rerun the command).
