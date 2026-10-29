# Fleet update verification after the cost-step fix (2026-10-29)

Operational dispatch + verification for commit `50964084` (the fix that made the
retired cost-removal step silent on converged hosts, so `cortex-update.sh` no longer
writes the stderr line that the fleet updater read as `❌ cortex-update failed`).

## Dispatch (all observed msg_ids, authoritative bus)

| Target | Action | corr | msg_id / result |
|--------|--------|------|------------------|
| esther (self) | UPDATE_REQUEST (self-test) | `selftest-50964084-1` | 0599604b-... — handler spawned detached worker, archived |
| moses | UPDATE_REQUEST | `hc-fix-50964084-moses` | def57ec5-... — archived by handler 06:15:07 UTC |
| titus | UPDATE_REQUEST | `hc-fix-50964084-titus` | c23104b3-... — archived 06:15:26 UTC |
| joseph | UPDATE_REQUEST | `hc-fix-50964084-joseph` | 3ead1d97-... — archived 06:20:10 UTC |
| gisu | UPDATE_REQUEST | `hc-fix-50964084-gisu` | 3864c46e-... — archived 06:20:08 UTC |
| kustos | UPDATE_REQUEST | `hc-fix-50964084-kustos` | 6114a6b2-... — archived 06:20:11 UTC |
| all 5 | FLEET_NOTICE (update fix landed) | `notice-50964084-<a>` | all queued; esther self-test consumed: "FLEET_NOTICE from esther — notified + archived", then "Sent FLEET_NOTICE_RESULT to inbox_moses (mid=090fa08a…)" |

Request/reply archives were queried on the AUTHORITATIVE bus (via ssh to the bus
host) — ecause esther's local postgres is a reports mirror.

## Directly verified (ground truth, not bus-transport)

- **moses** (ssh): repo at `50964084`; deployed `cortex-update.sh` carries the fix
  marker; its PATH python3 `/usr/bin/python3` cannot import ruamel; its config has 0
  cost keys; running the deployed `remove_cost_tracking` against a COPY of that config
  gave `rc=0`, `stderr` 0 bytes, real config md5 unchanged → `SILENT-on-a-converged-host`.
- **esther**: repo at `50964084`; deployed copy carries the fix; dogfood
  (`cortex-dogfood.sh --force`) PASSED; the four-direction deployed-path probe
  `docs/evidence/cortex-update-cost-step-2026-10-29.sh` passed (converged silent, keys
  dropped with a capable interpreter, keys survive + loud without one, pre-fix baseline
  fails).
- EXEC round-trip to moses returned (git-main-sync: on main, 0 behind / 0 ahead).

## Fleet state after the fix — EXEC verification (authoritative ground truth)

`hc exec <agent> cortex-doctor.py` round-trip on each host (this works even though the
UPDATE_RESULT bus path did not):

| Host | Branch | Tree | Repo sync | Deploy sync | Judgment |
|------|--------|------|-----------|-------------|----------|
| esther | main | clean | up to date | matches HEAD | ✅ updated, verified locally |
| moses | main | clean | up to date (0/0) | matches HEAD | ✅ updated, verified directly |
| titus | main | clean | up to date | matches HEAD | ✅ updated |
| gisu | main | clean | up to date | matches HEAD | ✅ updated |
| joseph | main | **6 uncommitted** | **9 behind origin/main** | matches HEAD | ⚠️ pull blocked by dirty tree |
| kustos | main | **1 uncommitted** | **22 behind origin/main** | matches HEAD | ⚠️ pull blocked by dirty tree |

joseph + kustos were sent UPDATE_REQUESTs (consumed/archived) but their `git pull`
refused on uncommitted changes — `git-main-sync.sh` on joseph reproduced the exact
refusal (`error: cannot pull with rebase: You have unstaged changes`). Both need their
working tree resolved by its owner (commit or stash the unknown edits), then re-run
`git-main-sync.sh`; a fast-forward pull then deploys via the post-merge hook. Not
performed here: I do not commit or stash a host's un-owned uncommitted work.

## Open observation — UPDATE_RESULT transport

All 6 UPDATE_REQUESTs were consumed and archived by their handlers, but NO
`UPDATE_RESULT` appeared on the authoritative bus (live or archives, 60-min window)
at the time of writing. This matches the documented "consumed but no result" fleet
pattern and is being followed up; it does NOT change that the fix is on origin/main
and each host's next pull deploys it. FLEET_NOTICE_RESULT transport worked from
esther (mid=090fa08a).

## Re-run
Sent with ~/.hermes-cortex/scripts/hc (UPDATE_REQUEST / FLEET_NOTICE). Verification:
ssh to the bus host and query `bus.messages` / `bus.archives` for the corr ids above.