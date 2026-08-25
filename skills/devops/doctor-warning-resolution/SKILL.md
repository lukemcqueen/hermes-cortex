---
name: doctor-warning-resolution
version: 1.0.0
category: devops
description: >-
  Use when fixing cortex-doctor naming/cron drift warnings.
author: Hermes Cortex
license: MIT
platforms: [linux, macOS]
---

# Doctor Warning Resolution

Use when the cortex-doctor emits a WARN or FAIL and you need to trace it
to the check function, understand what it validates, and fix all references.

## Investigation Pattern

Trace a doctor warning end-to-end:

1. **Read the warning message** — note the exact check label (e.g. "Script naming",
   "Script prefix", "Cron expected missing", "Cron extra"). The label matches
   the function that produced it.

2. **Find the check function** — open `ops/scripts/manage/cortex_doctor/checks.py`
   and search for the label string. Each check is a `def check_*` function that
   calls `res.add(label, severity, message, hint)`.

3. **Read the check logic** — understand what the function validates. Key checks:
   - `check_script_naming()` — validates cron name-to-script alignment
   - `parse_expected_crons()` — reads expected cron list from install script uninstall arrays
   - `parse_orch_crons()` — same for orchestrator install script

4. **Find the cron definition** — search `~/.hermes/cron/jobs.json` for the cron name.
   Read `name`, `script`, `schedule`, `deliver`, and `no_agent` fields.

5. **Check the install scripts** — search `install-crons.sh` and `install-orch-crons.sh`
   for the cron name. If not found, it was created ad-hoc (local-only cron).

6. **Search ALL cross-references** — grep the entire repo for the old name:
   docs, plists, skills, agent registries, manifest files, deployment scripts.
   A rename can touch 15-20 files.

7. **Apply fix** — rename/move files, update all references, update runtime cron.

8. **Deploy and verify** — `cortex-update.sh` then doctor with `--quiet`.

## Script Naming Checks (check_script_naming)

The function at `checks.py:2361` runs two independent checks on every cron
job that has both a `name` and a `script` field:

### Check 1: Name/Script match

```python
if not script_norm.startswith(name_norm) and not name_norm.startswith(script_norm):
    res.add("Script naming: <name>", "WARN", ...)
```

The script stem (filename minus extension) must either:
- Start with the cron name (e.g. `agent-foo.py` → cron `agent-foo`)
- OR be started by the cron name (e.g. `agent-foo.py` → cron `agent-foo-weekday`)

This allows shared scripts: `agent-foo-weekday` and `agent-foo-weekend` both
use `agent-foo.py` ✅

### Check 2: Prefix convention

```python
if name.startswith("agent-") and not script_stem.startswith("agent-"):
    res.add("Script prefix: <name>", "WARN", "script lacks 'agent-' prefix")
elif name.startswith("orch-") and not script_stem.startswith("orch-"): ...
elif name.startswith("local-") and not script_stem.startswith("local-"): ...
```

The cron prefix must match the script prefix. Only `agent-`, `orch-`, and
`local-` are checked — all others pass silently.

### Fix pattern for naming/prefix warnings

Rename the script so its stem (no extension) matches or starts with the cron
name AND carries the same prefix:

| Cron name | Old script | New script |
|-----------|-----------|------------|
| `local-health-push` | `health-vector-push.sh` | `local-health-push.sh` |
| `agent-foo-workday` | `foo.py` | `agent-foo-workday.py` |

### Pitfalls

- **Check 1 can pass while Check 2 fails** — e.g. script stem matches cron name
  but lacks the prefix. Both must pass silently for a clean doctor.
- **`local-*` crons are excluded from expected-cron checks** but NOT from
  script naming checks. A `local-*` cron with a mismatched script still fires.
- **Underscore normalization** — `_` and `-` are normalized to `-` for comparison
  (`agent-session_cache` matches `agent-session-cache`). The actual filename
  stays the same.
- **Script subdirectory is stripped** — `Path(manage/agent-foo.sh).stem` = `agent-foo`.
  The directory prefix doesn't participate in the check.

## Expected Cron Checks (parse_expected_crons / parse_orch_crons)

The doctor reads expected cron names from the **uninstall arrays** in
`install-crons.sh` and `install-orch-crons.sh`. It does NOT read the
create_cron blocks. This architecture creates a two-way sync requirement:

- **Cron in create_cron but NOT in uninstall array** → doctor silently ignores it
- **Cron in uninstall array but NOT in create_cron** → doctor reports "missing"
  but the cron still exists (not actually missing — just not in the installer)
- **Same name in both** → doctor validates correctly
- **Name mismatch between the two** → silent drift, untracked cron

After any rename cycle, run `fix-cron-duplicates.py` to verify sync:
```bash
python3 ~/hermes-cortex/ops/scripts/manage/fix-cron-duplicates.py
```
Zero issues = arrays are in sync.

## Multi-File Rename Workflow

When a renamed script is referenced across the repo (always assume this):

1. `git mv` the script to its new path
2. Update the script header comment (`# Formerly known as: old-name`)
3. Update `cortex-update.sh` register call
4. Update docs: `setup-reference.md`, `DOCS-INDEX.md`, `integration-audit.md`,
   `service-layer-decision.md`
5. Update skill docs: any skill that references the script path
6. Update agent registries: `agent-registry.template.json`, `agent-registry.json.example`
7. Update launchd/systemd templates if applicable
8. Update the runtime cron: `hermes cron edit <job-id> --script <new-name>`
9. Deploy: `cortex-update.sh`
10. Verify: `python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet`

## Common WARN patterns

| Warning label | Most likely cause | Fix |
|--------------|-------------------|-----|
| "Script naming: X" | Script filename doesn't share a base with cron name | Rename script to match cron name |
| "Script prefix: X" | Script filename lacks the cron's prefix (`agent-`, `orch-`, `local-`) | Rename script to add the prefix |
| "Cron expected missing: X" | Doctor expects X but it's not in the job list | Cron was removed or renamed without updating uninstall array |
| "Cron extra: X" | A live cron that isn't in any expected list | Rename to `local-<name>` (opt out) or add to uninstall array |
| "Cron status: X — last run: error" | X was interrupted mid-run by a cortex update purging its governance lock | Re-run via `cronjob action='run' job_id=<id>` (scheduler refresh, NOT manual script) |
| "MCP server (agent-bus): not configured" on a non-orch host | Register_orch service expected unconditionally in `EXPECTED_MCP_SERVERS` | Role-gate the check on `AGENT_ROLE == "orchestrator"` |
| "Stale deploy: scripts/agent-bus-mcp.py" on a non-orch host | Orch-only file deployed where it shouldn't be | Remove the file — it's a CORRECT warning, don't suppress it |

### 5. PENDING cycles owned by LIVE sessions — do NOT score them

When the doctor reports `❌ PENDING cycles`, some may belong to **other
sessions still running on the host** (concurrent agents mid-task). Scoring
someone else's active cycle corrupts their governance — their end_change will
find the cycle already consumed. Before scoring a foreign PENDING cycle:

1. `cycle_query(unreviewed=true)` — note each cycle's `session_id`
2. Check liveness: `ls ~/.hermes-cortex/state/.hermes-session-*.id` and
   `ps -p <pid>` for each (skip the `current` symlink)
3. Score ONLY cycles whose owning session is dead (stale) — leave live ones;
   they clear when the owning session closes its own cycle

A stale lock file (`.governance-<session>.json` with expired heartbeat) whose
owner pid is gone is safe to leave or purge; a PENDING cycle from a live pid is
never yours to touch.

### 6. Non-streaming cron API calls trip the 600s inactivity watchdog

LLM crons killed with `last_activity=waiting for non-streaming API response`
are not hung — cron turns are hardcoded non-streaming (deadlock fix #62151),
so a slow-but-alive DeepSeek response produces zero activity deltas and the
watchdog (default 600s) kills it before the API-side 1800s bound. Fix: raise
`HERMES_CRON_TIMEOUT` in `~/.hermes/.env` (e.g. 1800) — NOT reduce the timeout.
Full detail (code paths, dead-config trap, streaming as the real fix):
`references/cron-timeout-and-soul-trim-2026-08-03.md`.

## Post-Update Pitfalls (verified 2026-07-31)

These warnings appear right after a "pull latest / update cortex" session and are often misread as broken crons or configs.

### 1. Cron status error = interrupted in-flight run, not a broken cron

`cortex-update.sh` purges ALL governance locks — including a running cron session's lock. An in-flight LLM cron loses its lock mid-run and is marked interrupted:
```
gateway.run: Shutdown (post-interrupt): marked 1 in-flight cron job(s) interrupted: <job_id>
```
The doctor then reports `⚠️ Cron status (<name>) — last run: error` even though the cron itself is fine.

**Fix:** re-run the cron through the scheduler to refresh `last_status`:
```
cronjob action='run' job_id=<id>
```
A manual `python3 script.py` does NOT update the scheduler's status — only a scheduler run does.

### 2. Register_orch services must be role-gated in the doctor too

When a service is deployed via `register_orch` (orchestrator-only), the doctor's `EXPECTED_MCP_SERVERS` (in `cortex_doctor/config.py`) must also be role-aware — otherwise non-orch hosts get `FAIL: MCP server (agent-bus) not configured` while the file was never supposed to deploy there. Pattern used for the agent-bus MCP server:
```python
is_orch = AGENT_ROLE == "orchestrator"
if name == "agent-bus" and not is_orch:
    # WARN if present (leftover), PASS if absent
```
The stale-deploy check (`check_stale_deploys`) already skips `register_orch` entries on non-orch hosts — so an orch-only file present on a non-orch host is a *correct* warning: remove the file, don't suppress the warning.

### 3. MCP governance locks carry the WRONG repo_slug for commits

`loop-gov-mcp.py` derives `repo_slug` from the gateway's cwd via `git rev-parse`. If the gateway runs from inside `~/.hermes/hermes-agent` (a git repo), every MCP-created lock says `repo_slug: hermes-agent`. The pre-commit hook in `~/hermes-cortex` derives `repo_slug: hermes-cortex` and refuses to match:
```
❌ No active governance session.
```
...even though `check_lock` says the lock is active. The enforcer plugin accepts the lock (matches by session_id), but the pre-commit hook matches strictly by repo_slug.

**Fix (workaround):** the DB cycle is the source of truth; the lock file is disposable. Write a corrected lock mirroring the active session with the right slug:
```python
import json, os, glob
src = glob.glob(os.path.expanduser('~/.hermes-cortex/state/.governance-<session>.json'))
state = json.load(open(src[0]))
state['repo_slug'] = 'hermes-cortex'   # or the repo you're committing to
json.dump(state, open(os.path.expanduser('~/.hermes-cortex/state/.governance-hermes-cortex.json'), 'w'), indent=2)
```
**Report to Moses:** systemic flaw — the hook's hint ("cd into the repo before begin_change") is impossible from the MCP side since the MCP server derives the slug from the gateway process cwd, not the agent's terminal cwd.

### 4. Documentation rename = reference sweep, not just file move

Renaming a shared doc (e.g. `agent-bus-setup.md` → `orch-bus-setup.md`) touches every consumer: `DOCS-INDEX.md`, onboarding, runbooks, `docs/stale-paths-audit.md`, skill references, and even systemd `Documentation=` lines. Sweep `--include="*.md" --include="*.sh" --include="*.py" --include="*.yaml" --include="*.service"` and verify zero remaining matches before committing. Also: `git mv` fails with `destination exists` when the refactored target already exists (a prior partial rename) — check `git ls-files | grep <name>` first; if the target exists, the real work is `git rm` the stale duplicate + update all references to the surviving canonical file.

  inactivity-timeout incident (non-streaming cron turns vs 600s watchdog vs
  1800s API bound), `HERMES_CRON_TIMEOUT` fix, dead-config trap, SOUL.md
  >15K trim recipe (keep markers + scripture anchor), stale-retired-cron
  removal, and the live-session PENDING-cycle rule.
