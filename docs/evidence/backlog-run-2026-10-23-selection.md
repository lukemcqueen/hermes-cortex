# Backlog run — top-task selection + diagnosis (2026-10-23, `orch-bus-worker`)

Governance cycle **#13692**, session `cron_1954deb5ad76_20261023_082155`,
task id `remediate-apply-bounded-reports`. Host-derived identity: **esther**
(orchestrator).

## 1. Backlog pulled (repo=ALL — this host's rows + locally-present fleet rows)

```
pending (claimable): 16        pending (not claimable): 12
pending (story):      3        In review: none
blocked: 2 (66914fe1 [queue/1], 2fc4d871 [queue/3])   paused: 10
```

Top row by (priority desc, created_at) = `c579ef95`, priority 3, **kind=story**.
Its open children are `[cost/2]` `40cb307d` (cross-host config change, needs a
reviewed plan), `[cost/4]` `6b7d9b8a` (dispatched 2026-10-22 to 4 hosts,
consumed with no closure — issue #86), and the two `blocked` queue slices. No
unblocked, unattended-executable slice (the `orch-task-morning-pass` of
2026-10-23 measured the same state and reported the hold).

## 2. What was actioned, and why it qualifies

**Row `736a496b` — "Luke reported repeated identical deliveries from
agent-remediate-apply every 10 min (`service_down: Remote Agent Bus
unr…`)".** It is the first pending row in the sort order that is a real task
row, is orchestrator-local, and can be finished **and verified** unattended.

Its premise was tested, not assumed.

### 2.1 The repeated-delivery mechanism, reproduced on the PRE-FIX revision

`git show 57893ff2^:ops/scripts/agent/agent-remediate-apply.py` into a scratch
tree beside a copy of the current test, then run the suite there:

```
$ PYTHONPATH=~/hermes-cortex/ops/scripts python3 <scratch>/tests/test_agent_remediate_apply.py
FAIL (3):
  - 1 timestamp-insensitive: ids differ 'service_down|Remote Agent Bus unreachable|2026-08-31T00:20:20Z' != 'service_down|Remote Agent Bus unreachable|2026-08-31T00:30:20Z'
  - 3b second run silent: rc=0 out='[2026-10-23 08:25:47 KST] agent-remediate-apply:\n  ❌ 1 issue(s) could not be fixed\n     - service_down: Remote Agent Bus unreachable\n'
  - 3c handler invoked 2x (expected exactly 1): ['sudo systemctl restart cortex-bus …', 'sudo systemctl restart cortex-bus …']
prefix rc=1
```

That is the report reproduced exactly: the volatile per-run sensor timestamp
was part of the dedup key, so every 10-minute tick re-minted the id, re-ran the
handler and re-delivered the identical failure line forever. It was fixed on
2026-08-31 by `57893ff2` ("drop volatile timestamp from issue dedup key").

### 2.2 Same test on the CURRENT revision — PASS

```
$ cd ~/hermes-cortex && python3 tests/test_agent_remediate_apply.py
PASS — agent-remediate-apply: 5/5 (timestamp-insensitive id, detail-sensitive id,
main() reports once then silent, paused-cron auto-resume + watchdog gate + never-resume)
rc=0
```

### 2.3 The deployed (ACTIVE) artifact behaves the same way

A disposable probe (`~/.hermes/cache/scratch/ara_probe.py`, no TDD cycle —
throwaway inspection) loads the **deployed** `~/.hermes-cortex/scripts/agent-remediate-apply.py`
with an isolated `HOME`, plants a persistent `disk_low` issue and drives
`main()` three times:

```
=== DEPLOYED  size=18581  issue_id='disk_low|PROBE persistent disk_low condition'
  run1: rc=0 out='[2026-10-23 08:25:10 KST] agent-remediate-apply:\n  ❌ 1 issue(s) could not be fixed\n     - disk_low: PROBE persistent disk_low condition'
  run2: rc=0 out=''
  run3: rc=0 out=''
  seen file exists: True 'disk_low|PROBE persistent disk_low condition\n'
```

Reports once, then silent — the active path no longer repeats. `diff` against
the repo copy shows the deployed file differs only by the 3-line deploy banner
(`SOURCE:` / `Do NOT edit`), and its mtime (2026-10-23 04:46) shows the deploy
is current: this is not a deployed-vs-repo drift case.

## 3. The change (this cycle)

The **guard** for that bug had gone RED on healthy code, so nothing was
protecting the fix: test case `3c` counted every `run_cmd` call, and the
unconditional enforcement-relock step (added 2026-10-02 in `ee8440d8`) adds its
own `hermes-plugin-lock status` call to that list.

```
$ python3 tests/test_agent_remediate_apply.py      # before this change
FAIL (1):
  - 3c handler invoked 3x (expected exactly 1): ['hermes-plugin-lock status',
    'sudo systemctl restart cortex-bus …', 'hermes-plugin-lock status']
rc=1
```

`3c` now counts the **handler's own** command (`systemctl restart …`), which is
what "not re-invoked for an identical issue" means — and the assertion still
fails on the buggy revision (§2.1: `3c handler invoked 2x`), so it is a live
guard, not a happy path with a name.

## 4. Left open (reported, not silently dropped)

1. **`agent-remediate-apply` is PAUSED on this host** — `enabled=false,
   state=paused, paused_at=2026-09-23T03:51:03+09:00` (`~/.hermes/cron/jobs.json`
   job `1c86b9471c16`), i.e. it has not run for a month. Two consequences:
   (a) the **relock-after-inactivity guarantee** documented in
   `governance-lock-lifecycle` (§Guarantees, `ee8440d8`) has had no executor on
   this host since 2026-09-23; (b) the deterministic sensor fixers
   (disk/nginx/ollama/web-cache) are not applied. The applier is not on its own
   `NEVER_RESUME` denylist, so a future auto-resume would pick it up. **Not
   re-enabled unattended** — a paused cron is an operator decision, and the
   re-enable should follow this deploy (the fix's own delivery shape changes
   only once the job runs). Recorded as a task row with the decision owed to Luke.
2. **Residual repeat source, not in this cycle's scope:** the auto-resume
   notice (`✅ Resumed paused cron '<name>'`) still re-emits every
   `RESUME_COOLDOWN_HOURS` (6h) for as long as a permanently broken job keeps
   failing — bounded, but unbounded in total, and with no escalation line. A
   per-job attempt cap plus a one-shot escalation is the right shape
   (`watchdog-alert-design`); it is a separate row.
3. **`orch-daily-regression-gate` fails daily** (`job d39c3b3eca5d`, ran
   2026-10-23 03:15, `last_status=error`): the delivered
   `sustainability-briefing-2026-10-22.md` fails the canonical checker —
   `[sources] source lines=0 (>= 13) FAIL`, `[words] count=1364 (600-1200) FAIL`,
   `[binary] docx+pdf carry briefing text FAIL`. Tracked as its own row; it is a
   client-facing deliverable (Amy's daily briefing), so it is not left as prose.

## 5. Re-run

```bash
cd ~/hermes-cortex && python3 tests/test_agent_remediate_apply.py    # expect PASS, rc=0
python3 ~/.hermes/cache/scratch/ara_probe.py                         # expect run2/run3 empty
```
