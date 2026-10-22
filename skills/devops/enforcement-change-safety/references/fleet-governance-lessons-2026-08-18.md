# Fleet Governance Lessons — 2026-08-18 (watchdog fix dispatch + deadlock cleanup)

Two durable facts learned while verifying a fleet `UPDATE_REQUEST` dispatch
of the MCP watchdog fix (commit b7678169) and cleaning up after the
2026-08-18 MCP deadlock.

## 1. Loop-governance DBs are per-host — you cannot score a sibling's leaked cycles

The doctor check `PENDING cycles | N unscored cycle(s) from finished
task(s)` flags cycles whose task has no active lock (a leak). The loop DB
each host's `cycle_query`/`feedback_accept` reads is that HOST's local DB:

- The orchestrator's `cycle_query(status="pending")` does NOT see a
  sibling host's leaked cycles — they are not in the orchestrator's DB.
- The fix must run ON the owning host: send the owner a bus message
  (`hc send <agent> "COMMAND: score leaked PENDING cycles" ... --self-tested`)
  listing the cycle IDs (task_id + session-id prefix as shown by their
  doctor) with the instruction: score each via `feedback_accept` (decision
  correct), then re-run doctor to confirm 0 fail.
- Evidence: moses (3 cycles: skill-curation-2026-08-18#1,
  orch-skill-evaluate-2026-08-18#1, cortex-bus-tick-0818#1) and titus
  (4 cycles: skill-curation-mcp-deadlock-*, skill-client-*) both leaked
  cycles when the MCP deadlock blocked `end_change`; their UPDATE_RESULT
  doctors FAILed on exactly this while the update itself landed fine.
- **UPDATE_RESULT `success:false` with only a leaked-cycle doctor FAIL is
  NOT a failed update** — the SHA moved, the deploy landed, the receipt is
  just honest about the doctor. Fix the cycles, don't re-dispatch.

## 2. Deploy-sync ordering: commit → cortex-update.sh → push

The doctor's `Deploy sync` check compares `~/.hermes-cortex/state/update-commit`
(last deployed commit) against git HEAD. Running `cortex-update.sh` BEFORE
committing leaves `update-commit` pointing at the old HEAD, so the pre-push
dogfood gate blocks with:

```
❌ Deploy sync
  HEAD (b7678169) ahead of last deploy (5f4fd062) — 1 commit(s) not deployed
```

The dogfood gate does NOT fix this itself — it reports the failure and
blocks the push. Correct order for script/config changes in hermes-cortex:

1. `git commit` (pre-commit scores + adversarial gate)
2. `bash ops/scripts/cortex-update.sh` (deploys the committed state, writes
   `state/update-commit` = new HEAD)
3. `git push` (dogfood re-verifies; `Deploy sync` PASS)

Deploying pre-commit is the trap: the deploy writes update-commit for the
OLD head, then the commit moves HEAD → stale. If the gate blocks you, the
fix is exactly one `cortex-update.sh` run (no code change needed), then push.
