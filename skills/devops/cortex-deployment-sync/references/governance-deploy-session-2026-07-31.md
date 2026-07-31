# Governance Deploy Session Trace — 2026-07-31

Full reproduction of the immutable-governance-file deploy failure and the proper recovery path. KOSCAP staging server (Linux, Ubuntu 24.04).

## Trigger

User: "pull latest and cortex update!" → `git pull --rebase origin main` failed with uncommitted changes (a non-orchestrator edit to `ops/install/deploy/docker-compose.langfuse.yml` — orchestrator-only path, pre-commit hook blocks non-orch commits).

## What happened

1. **Stash the uncommitted orchestrator-only edit** before pulling:
   ```
   git stash push -m "gisu: POSTHOG_HOST fix (orchestrator-only, pending Moses)" -- ops/install/deploy/docker-compose.langfuse.yml
   ```
2. **Pull conflict on `blocked_ips.add`** — auto-generated pipeline IP list, conflicted twice in the same session (two separate pulls). Resolved both with `--theirs`.
3. **`cortex-update.sh --force-all` printed 7 FAILED lines:**
   ```
   FAILED: /home/luke/.hermes/plugins/governance-enforcer/__init__.py
   FAILED: /home/luke/.hermes-cortex/scripts/pre-commit-score
   FAILED: /home/luke/.hermes-cortex/scripts/pre-push-pull
   FAILED: /home/luke/.hermes-cortex/scripts/post-commit-audit
   FAILED: /home/luke/.hermes-cortex/scripts/post-push-audit
   FAILED: /home/luke/.hermes-cortex/hooks/post-merge
   FAILED: /home/luke/.hermes-cortex/scripts/hermes-plugin-lock
   cp: cannot create regular file '.../hermes-plugin-lock': Operation not permitted
   ```

## Root cause

All 7 files carry `chattr +i` (immutable). The `i` flag survives `chmod` — files show mode `-r--r--r--` but lsattr reveals `----i---------e-------`. A plain `cp` cannot open them for writing.

`cortex-update.sh` has the full unlock→copy→re-lock cycle in `deploy_governance_plugin()` — it calls `sudo hermes-plugin-lock unlock` before copying. This requires a NOPASSWD sudoers rule for `/usr/local/sbin/hermes-plugin-lock`, which EXISTS on this host (`(root) NOPASSWD: /usr/local/sbin/hermes-plugin-lock`). The first `--force-all` run had failed before reaching the plugin deploy; the register loop that handles the other 6 files has no unlock step of its own.

## Recovery (the proper path)

```bash
# 1. Confirm immutability
lsattr ~/.hermes/plugins/governance-enforcer/__init__.py
#    ----i---------e-------  ← immutable

# 2. Verify NOPASSWD rule exists
sudo -n -l | grep hermes-plugin-lock

# 3. Clear flags
sudo -n hermes-plugin-lock unlock
#    UNLOCKED: ...governance-enforcer/__init__.py
#    UNLOCKED: ...pre-commit-score  (etc.)

# 4. Re-run deploy
cd ~/hermes-cortex && bash ops/scripts/cortex-update.sh --force-all

# 5. Verify
diff ~/hermes-cortex/plugins/governance-enforcer/__init__.py ~/.hermes/plugins/governance-enforcer/__init__.py   # empty
hermes plugins list | grep governance    # enabled
lsattr ~/.hermes/plugins/governance-enforcer/__init__.py   # ----i---------e-------  ← re-locked
grep -n "adversarial\|pycache" ~/.hermes/plugins/governance-enforcer/__init__.py   # new features present
```

## Post-deploy fallout: lock purge + PENDING cycles

`cortex-update.sh` runs `purge-stale-governance-locks.py` at the end, deleting EVERY `.governance-*.json` lock — including the session's own. Consequences:

- `end_change()` after the update says "No governance session active. Nothing to release."
- The doctor reports `❌ PENDING cycles` — cycles created by `begin_change()` calls that were never scored
- Next `begin_change()` creates a new cycle; the DB is the source of truth, not the lock file

**Fix:** after each deploy, `begin_change` → `cycle_query(task_id)` → `feedback_accept(cycle_id=N, note=...)` for EVERY pending cycle → `end_change`. Verify with another doctor run.

## User directives captured this session

1. "whenever there's a governance mechanism change you NEED to cortex update as this is the proper path. no shortcuts." — the immutable-file deploy is the canonical example.
2. "DO NOT UPDATE SOURCE" — during pull-latest/doctor-fix, don't modify repo source to silence warnings. Accept non-failure warnings (SOUL.md reverse drift, skill drift) as-is.
3. "rerun simply" / "just run it simply!" — for the doctor re-run, use the plain `cortex-update.sh` invocation, not repeated `--force-all` cycles.

## Related

- The wrong `POSTHOG_HOST: "http://127.0.0.1:1"` advice that lived in `langfuse-self-hosted` (user-owned) is documented in `linux-performance-diagnostics` territory as a telemetry retry-storm spin — see the session's performance-audit findings.
