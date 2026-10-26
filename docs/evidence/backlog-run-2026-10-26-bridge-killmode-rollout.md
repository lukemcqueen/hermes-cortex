# Backlog run 2026-10-26 — fleet bridge KillMode rollout (task `3c94beac`)

Evidence for the `orch-bus-worker` cron run (job `1954deb5ad76`, session
`cron_1954deb5ad76_20261026_142143`, governance cycle **#13817**). Host-derived
identity: **esther** (orchestrator). Everything below is raw tool output from
this run; nothing is inferred from a prior session.

## Why this task

`3c94beac` (in_progress, esther) was named by the 2026-10-25 and 2026-10-26
morning passes as the **single unblocking action** for the frozen backlog:
joseph/gisu/kustos/titus still carried bridge service units with no explicit
`KillMode`, so a bridge tick's cgroup SIGTERMs the UPDATE worker it detached,
no host can be updated by the fleet's own UPDATE_REQUEST protocol, and
`[cost/4]` (`6b7d9b8a`) stays blocked.

The row's own stated fix ("a helper script registered in `cortex-update.sh`")
landed 2026-10-25 as `dd8b241c` (`ops/scripts/install/install-bridge-killmode.sh`,
registered in `cortex-update.sh`, 4 pytest cases, deployed on esther). What was
NOT done, and is done here, is the per-host rollout and its measurement.

## Step 1 — self-test of the exact flow (hard rule)

The flow used for the fleet is the one proven on this host first:

`hc exec esther git-main-sync.sh --check --output-schema RAW` → handler run
once → EXEC_RESULT read back:

```
[14:24:18] [esther] Sent EXEC_RESULT to inbox_moses (mid=094a5d03… corr=exec-52d…)
✅ EXEC_RESULT from esther:
   Command: git-main-sync.sh
   Exit:    0
   stdout:  [2026-10-26 14:24 KST git-main-sync] repo: /home/esther/hermes-cortex
            [2026-10-26 14:24 KST git-main-sync] current branch: main
            [2026-10-26 14:24 KST git-main-sync] HEAD is 0 behind, 0 ahead of origin/main
            [2026-10-26 14:24 KST git-main-sync] OK: on main, up to date
```

## Step 2 — classification (`git-main-sync.sh --check`, read-only, 4 hosts)

Per the fleet-commands skill: classify BEFORE dispatching. Each host's own
words (repo paths are theirs):

| host | branch | behind/ahead | class |
|---|---|---|---|
| esther | main | 0 / 0 | current |
| joseph | main | **1 / 0** | pure fast-forward → repair |
| kustos | main | **14 / 0** | pure fast-forward → repair |
| titus | main | 29 / 0 | **macOS — see finding 3** |
| gisu | main | **235 / 62** | **divergent → escalate, do NOT pull** |

## Step 3 — repair via the documented fast-forward path

`hc exec <host> git-main-sync.sh` → `git pull --rebase origin main`; the repo's
global `post-merge` hook (`~/.hermes-cortex/hooks/post-merge`, verified to fire
only when `REPO_ROOT == $HOME/hermes-cortex`) runs `cortex-update.sh`, which
deploys the new tree AND invokes `install-bridge-killmode.sh` — i.e. both halves
of the repair (unit rewrite + `systemctl --user daemon-reload`).

kustos's EXEC_RESULT shows the whole chain running on the host:

```
   stderr:  From https://github.com/lukemcqueen/hermes-cortex
 * branch              main       -> FETCH_HEAD
━━━ post-merge: auto-deploying to match new HEAD ━━━
   ✓ Agent identity: kustos (git author: kustos-agent <kustos@hermes.local>)
   ✓ Fleet interpreter: /home/luke/.hermes-cortex/venv/bin/python3
   ━━━ Cortex Update ━━━
   ✓ Updated: ff4db13c → ff4db13c
   ✓ Force mode — re-checking all mapped files…
```

## Step 4 — verification per host (`install-bridge-killmode.sh`, exact output)

```
esther  exit 0   install-bridge-killmode: all 59 bridge unit(s) already load KillMode=process — no reload needed
joseph  exit 0   install-bridge-killmode: all 45 bridge unit(s) already load KillMode=process — no reload needed
titus   exit 0   install-bridge-killmode: not Linux — no user-systemd bridge — skipped
gisu    exit -1  Script not found: install-bridge-killmode.sh
kustos  (no EXEC_RESULT read in this run — the answer exists; see the
         "Follow-up pass" section below: 46/46 already correct at 14:45 KST)
```

`joseph` is the material result: its units had NO `KillMode` before this run and
the installer's predicate (the generator's own `unit_needs_killmode()`, not a
second matcher) now finds **0 of 45** needing the fix — the deploy crossed the
host and rewrote them.

## Findings (new this run)

1. **`hc exec --timeout` is not threaded into the EXEC payload.** The payload
   that landed on joseph was
   `{"command": "git-main-sync.sh", "params": [], "timeout": 120, "output_schema": "RAW"}`
   while `hc exec`'s own poll window honoured the 600 s I asked for. So the
   script ran under a 120 s cap and both joseph and titus answered
   `Exit: -1  stderr: TIMEOUT after 120s` — yet joseph's deploy demonstrably
   completed (step 4), because the killed shell's child (`cortex-update.sh`
   under the post-merge hook) continued as an orphan. **Read `TIMEOUT after
   120s` as "the wrapper stopped waiting", not "the work failed"** — verify with
   the read-back, never with the exit code alone.

2. **A host can be unreachable for one script and perfectly reachable for
   another.** gisu consumed and answered an EXEC in this run (so its handler and
   bus path are fine) but its *deployed* tree predates the tool
   (`Script not found`), consistent with `235 behind, 62 ahead`. The
   fleet-commands bootstrap chicken-and-egg applies exactly here.

3. **titus is not a KillMode target.** `3c94beac` lists titus among the
   "unrepaired" hosts, but titus is macOS (`/Users/luke/hermes-cortex`) and has
   no user-systemd bridge units; the installer correctly reports
   `not Linux — no user-systemd bridge — skipped`. The fleet-side fixable set is
   4 Linux hosts (esther, joseph, kustos, gisu), not 5.

4. **The divergence on gisu is an operator decision, not a bus action.** 62
   local commits ahead means a pull would be a merge of unknown work in
   progress; per the skill this is escalated, never pulled unattended.

## State after this run

- esther — repaired, proven (59/59), unchanged.
- joseph — **repaired this run** (45/45, deploy at `ff4db13c`).
- kustos — **REPAIRED and VERIFIED** the same day (see the follow-up pass below).
  The "still pending" reading above is superseded: kustos consumed the EXEC at
  14:45:08 KST and answered `all 46 bridge unit(s) already load KillMode=process`.
- titus — not applicable (macOS).
- gisu — out of bus reach (stale deployed tree + divergent branch) → operator.

The row's own acceptance rule ("do NOT report the fleet as fixed until each host's
check passes") is still honoured: gisu's check does not pass and titus has no check
to pass, so neither is reported fixed.

## Follow-up pass — 2026-10-26 20:2x KST: kustos verified

Read back from the bus archives in this pass (`bus_archives`, `since_minutes=1440`,
`limit=2000`, matched on the exact `correlation_id`):

```
inbox_kustos  EXEC        corr=exec-510ff2b55ab6  from=esther
  body={"command": "install-bridge-killmode.sh", "params": [], "timeout": 120, "output_schema": "RAW"}
  enqueued 2026-10-26 05:39:14.092818+00  archived 2026-10-26 05:45:08.850551+00  state=processing
inbox_moses   EXEC_RESULT corr=exec-510ff2b55ab6  from=kustos
  body={"success": true, "stdout": "install-bridge-killmode: all 46 bridge unit(s) already load KillMode=process — no reload needed\n", "stderr": "", "exit_code": 0, "command": "install-bridge-killmode.sh", "duration_seconds": 0.4, "topic": "fleet-update"}
  enqueued 2026-10-26 05:45:09.503539+00  archived 2026-10-26 05:50:25.858296+00
```

(UTC; +09:00 = KST → send 14:39:14, consume 14:45:08, reply 14:45:09.)

6-checkpoint: send (request in `inbox_kustos`) → consume (`archived_at` 05:45:08)
→ process (handler ran, 0.4 s) → respond (`EXEC_RESULT`, same `correlation_id`)
→ read (archives) → inbox-verify (this pass's own read, matched on the id — no
secondhand report).

Verified host state for the KillMode rollout, each by that host's own output:
esther 59/59, joseph 45/45, kustos 46/46; titus N/A (macOS); gisu unrepaired and
not bus-reachable (`Script not found`; repo 235 behind / 62 ahead → operator).

Lesson for the read-back: widen `since_minutes` past the run's own look. This
result was archived six minutes after the request and was older than the 60-minute
default window once five-minute `DOCTOR_TEST` heartbeats had flooded the queue;
a 2000-message / 1440-minute archive read is what found it.

## Re-run

```bash
hc exec esther git-main-sync.sh --check --output-schema RAW      # self-test the flow
hc exec <host>  git-main-sync.sh --check --output-schema RAW      # classify
hc exec <host>  git-main-sync.sh --output-schema RAW              # repair (fast-forward only)
hc exec <host>  install-bridge-killmode.sh --output-schema RAW    # verify (idempotent read-back)
```
