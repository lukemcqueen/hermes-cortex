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

## Full test suite — the whole repository, at 2b45a13d

The suite could not complete before these fixes (it aborted at 37%: the fact-retention
compressor tests re-execed the interpreter through the Hermes launcher with pytest s
argv). Now:

```
$ python3 -m pytest tests/ -q -p no:cacheprovider

======================= 1376 passed in 335.20s (0:05:35) =======================

# the same command before the pre-existing fixes: 6 failed, 1365 passed, run aborted
```

The four failures it started with were reproduced at the pre-change revision
(`git worktree add /tmp/pre-cost e5227fa7^` -> "4 failed, 26 passed"), which is how they
were classified as pre-existing rather than caused by the removal. All four are now fixed
and asserted in the tree (see the relevant test files and
docs/evidence/task-queue-remediation.md for the measured before/after).
