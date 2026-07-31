---
name: enforcer-modification-considerations
version: 1.0.0
category: devops
description: "Use before modifying any enforcer/governance code."
author: Moses
platforms: [linux, macos]
---

# Enforcer Modification Considerations

**Load this skill BEFORE modifying `plugins/governance-enforcer/__init__.py`, `mcp-servers/loop-gov-mcp.py`, or any governance enforcement code.**

---

## 1. Session Types — Know Your Prefixes

Hermes creates sessions with different ID prefixes depending on the session type. Every guard in the enforcer must cover ALL non-interactive prefixes.

| Prefix | Source | Can overwrite marker? | Guard needed? |
|--------|--------|-----------------------|---------------|
| `20260730_...` (date-based) | Interactive Telegram/DM | Yes (should own the marker) | No (primary user) |
| `cron_...` | Scheduled cron job | No — blocked by daemon guard | Yes |
| `bg_...` | Background subagent (delegate_task, etc.) | No — blocked by daemon guard | Yes |
| `cli`-source date-based | CLI-invoked session (cron/terminal `hermes` runs) | Blocked by sticky-lock (P1-A) | Yes — protected via lock |

**P1-A fix (2026-07-31):** the shared `.skills-loaded` marker race (any concurrent session stomping it mid-task) is now neutralized by the **sticky-marker-per-governance-lock** rule: `_check_skills_loaded_marker()` accepts a valid `session:*` marker when the session holds an active governance lock. The lock is stronger proof of discipline than the marker. Locks also carry `session_type` (cron/bg/interactive) and purge loops never delete unparseable (mid-write) lock files.

**Rule:** When adding a session-type guard, use `session_id.startswith("cron_") or session_id.startswith("bg_")`. Do NOT create separate `is_cron` and `is_bg` booleans — future prefixes will be missed.

**Guard locations in the enforcer:**
- `_auto_create_skills_marker()` — prevent daemon overwrite of `.skills-loaded`
- `_check_skills_loaded_marker()` — allow daemons to accept any `session:*` marker
- `_on_session_start()` — skip bootstrap when marker exists

**Checklist when modifying:**
- [ ] Search for ALL existing prefix guards: `grep -n 'cron_\|bg_' plugins/governance-enforcer/__init__.py`
- [ ] Does the guard also apply to `bg_` sessions?
- [ ] Is there a NEW session prefix we don't know about yet? Make the guard generic if possible (e.g., `not session_id.startswith("2026")` as fallback).

---

## 2. The DOGFOOD Chicken-and-Egg

The `begin_change()` MCP tool has a DOGFOOD check: if the deployed enforcer (`~/.hermes/plugins/governance-enforcer/__init__.py`) differs from the repo source (`plugins/governance-enforcer/__init__.py`), `begin_change()` rejects the request.

**The problem:** This blocks a new change when the mismatch is caused by ANOTHER agent's commit arriving via `git pull` — not by un-deployed local work.

**How to break the loop:**
1. `rm -f ~/.hermes-cortex/state/.skills-loaded` (clear stale marker)
2. Load all 8 always-section skills: `skill_view()` calls
3. Run `bash ~/hermes-cortex/ops/scripts/cortex-update.sh --force-all` (deploy the latest enforcer from repo)
4. `begin_change()` should now succeed

**If that fails** (e.g., terminal blocked because no lock):
- Trigger the pre-commit hook's auto-deploy: make a trivial commit (e.g., touch a doc file)
- The pre-commit hook's DOGFOOD check copies the enforcer from repo to deployed
- Commit succeeds, enforcer is now in sync
- Then proceed with `begin_change()` for the real work

**Permanent fix (future):** Add auto-deploy to the DOGFOOD check in `begin_change()`. When the enforcer differs from HEAD, copy it before blocking.

---

## 3. The Skills-Loaded Marker Race

The `.skills-loaded` file at `~/.hermes-cortex/state/.skills-loaded` is a single file. ALL concurrent Hermes sessions write to it. When session B loads skills, it overwrites session A's marker. Session A's writes are then blocked because `_check_skills_loaded_marker()` sees session B's ID.

**Session types that race:**
- Interactive session (you) — `session:20260730_142641_0dafe4a4`
- Background subagent — `session:bg_163714_c841c8`
- Cron session — `session:cron_b33bc9b07c55_...`

**How the daemon guard fixes this:**
- `_auto_create_skills_marker()`: if session starts with `cron_` or `bg_` and ANY marker exists, do NOT overwrite
- `_check_skills_loaded_marker()`: if session starts with `cron_` or `bg_` and marker is `session:*`, return True (accept any)
- Result: the first interactive session to load skills "owns" the marker for its entire lifetime

**If your writes are blocked (the marker has a different session ID):**
```
cat ~/.hermes-cortex/state/.skills-loaded
```
→ `session:bg_163714_c841c8` (not your session)

**Fix:**
1. `rm -f ~/.hermes-cortex/state/.skills-loaded` (clear stale marker)
2. Load all 8 always-section skills → marker recreated with YOUR session ID
3. Write tools unblocked

**Watch out:** If a daemon session (cron or bg) is still running, it may re-overwrite the marker. Work fast, or kill the daemon process first.

---

## 4. Multiple Repos, One Hermes

When a single Hermes installation manages multiple repos (e.g., hermes-cortex + other projects), the `repo_slug` field in governance lock files must be derived dynamically, not hardcoded.

**The problem:**
- Lock file at `~/.hermes-cortex/state/.governance-{session_id}.json` contains `"repo_slug": "hermes-cortex"`
- The pre-push hook expects `"hermes-cortex"`
- If the agent cloned the repo as `hermes-agent` (different name), the slug won't match

**Fix:**
- Shell scripts that create manual locks: derive slug from `basename "${CORTEX_REPO:-${HOME}/hermes-cortex}"`
- Python/MCP: use `_derive_repo_slug()` which runs `git rev-parse --show-toplevel` and takes the directory basename

**Files to check:**
- `ops/scripts/manage/agent-nginx-threat-pipeline.sh` — hardcoded slug (fixed)
- `ops/scripts/agent/agent-ip-submission.sh` — hardcoded slug (fixed)
- `plugins/governance-enforcer/__init__.py` — dynamic via `_derive_repo_slug()` ✓
- `ops/scripts/pre-commit-score` — dynamic via `git rev-parse` ✓

**Search pattern for hardcoded slugs:**
```bash
grep -rn '"repo_slug"' ops/scripts/ plugins/
```

---

## 5. Stale Hooks Allow Orchestrator Path Bypass

The pre-commit hook enforces orchestrator-only paths (from `docs/orchestrator-only-paths.txt`). If an agent has stale hooks (hasn't run `cortex-update.sh` after the guard was added), non-orchestrators can modify restricted paths like `plugins/`, `skills/`, `ops/scripts/`.

**The fix chain:**
1. Doctor's `check_hook_drift()` detects deployed hooks that differ from repo source
2. Agent runs `cortex-update.sh` to redeploy hooks
3. Pre-commit hook now blocks non-orch modifications to restricted paths

**If you're adding a new restricted path:**
1. Add to `docs/orchestrator-only-paths.txt`
2. Verify it's covered by `AGENTS.md` which lists the canonical restricted paths
3. The pre-commit hook reads the file at commit time — no code change needed

---

## 6. DOGFOOD Auto-Deploy vs `cortex-update.sh`

Two mechanisms deploy the enforcer:

| Mechanism | Trigger | How | Caveat |
|-----------|---------|-----|--------|
| Pre-commit DOGFOOD | `git commit` | Copies repo → deployed + unlock/lock | Only runs during commits |
| `cortex-update.sh` | Manual run | `deploy_governance_plugin()` function | Runs at end of deploy cycle |

**The DOGFOOD auto-deploy is faster but only works during commits.** If another agent's enforcer change arrives via `git pull`, the DOGFOOD check in `begin_change()` blocks you because the deployed copy is stale. Run `cortex-update.sh` to sync.

---

## 7. Testing Enforcer Changes

When modifying the enforcer, test these scenarios:

- [ ] **Interactive session:** write tools work with correct marker
- [ ] **Cron session:** marker NOT overwritten if one already exists
- [ ] **Background session (`bg_`):** same guard as cron
- [ ] **Multiple concurrent sessions:** daemon sessions don't steal the marker
- [ ] **No marker exists:** daemon sessions CAN create one (first boot scenario)
- [ ] **DOGFOOD sync:** deploy via `cortex-update.sh` — does `begin_change()` work?
- [ ] **Cross-machine pull:** another agent's enforcer commit arrives via pull — does DOGFOOD handle it?

**Quick test for daemon guard:**
```bash
echo "session:test" > ~/.hermes-cortex/state/.skills-loaded
# Then check: do cron/bg sessions respect the guard?
```

---

## References

- `plugins/governance-enforcer/__init__.py` — the enforcer itself
- `docs/orchestrator-only-paths.txt` — restricted paths
- `ops/scripts/pre-commit-score` — pre-commit hook with orchestrator guard
- `ops/scripts/manage/cortex_doctor/checks.py` — doctor checks (hook drift, enforcer permissions)
- `ops/scripts/cortex-update.sh` — deploy script with `deploy_governance_plugin()`
- `skills/devops/cortex-preflight/SKILL.md` — Pitfall 3 covers skills-loaded marker
