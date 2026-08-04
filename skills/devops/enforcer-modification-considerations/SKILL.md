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

| Prefix | Source | Marker behaviour (per-session, 2026-08-01+) |
|--------|--------|-----------------------------------------------|
| `20260730_...` (date-based) | Interactive Telegram/DM / CLI | Owns its own marker file — never touches other sessions' |
| `cron_...` | Scheduled cron job | Owns its own marker (bootstrap-created) |
| `bg_...` | Background subagent (delegate_task, etc.) | Owns its own marker |
| `cli`-source date-based | CLI-invoked session (cron/terminal `hermes` runs) | Owns its own marker |

**Per-session markers (2026-08-01):** the shared `.skills-loaded` file race is
**structurally eliminated** — each session writes its own proof at
`state/skills-loaded/<session_id>`, so no session can ever stomp another's.
The entire guard class bolted onto the shared file (daemon guard, subagent
guard, sticky-marker-per-governance-lock) is obsolete and was removed.
This was gap-doc P1-A candidate #3 ("per-session marker files"), the
documented structural fix.

**Rule:** When adding a session-type guard, use `session_id.startswith("cron_") or session_id.startswith("bg_")`. Do NOT create separate `is_cron` and `is_bg` booleans — future prefixes will be missed.

**Guard locations in the enforcer:**
- `_auto_create_skills_marker()` — writes `state/skills-loaded/<session_id>` (atomic temp+rename)
- `_check_skills_loaded_marker()` — reads THIS session's own marker; exact content match
- `_on_session_start()` — cron bootstrap creates the cron session's OWN marker

**Checklist when modifying:**
- [ ] Search for ALL existing prefix guards: `grep -n 'cron_\|bg_' plugins/governance-enforcer/__init__.py`
- [ ] Does the guard also apply to `bg_` sessions?
- [ ] Is there a NEW session prefix we don't know about yet? Make the guard generic if possible (e.g., `not session_id.startswith("2026")` as fallback).

---

## 2. The DOGFOOD Chicken-and-Egg

The `begin_change()` MCP tool has a DOGFOOD check: if the deployed enforcer (`~/.hermes/plugins/governance-enforcer/__init__.py`) differs from the repo source (`plugins/governance-enforcer/__init__.py`), `begin_change()` rejects the request.

**The problem:** This blocks a new change when the mismatch is caused by ANOTHER agent's commit arriving via `git pull` — not by un-deployed local work.

**How to break the loop (fixed 2026-08-04 — the sanctioned command is now lock-free):**

1. Run the sanctioned recovery — the enforcer allows this EXACT command
   without a governance lock:
   ```bash
   bash ~/hermes-cortex/ops/scripts/cortex-update.sh
   ```
   (No sudo, no chaining, no other flags beyond
   `--dry-run/--status/--delta/--clean-stale` — the
   enforcer's `_is_sanctioned_cortex_update_command()` matches exactly.)
2. Load all 8 always-section skills: `skill_view()` calls
3. `begin_change()` should now succeed (repo == deployed)

**If the skills gate blocks the terminal call** (no skills marker yet):
- Load the 8 always-skills first, then re-run the command above.

---

## 2a. Hooks Fire in Project Repos Too — Never Assume the Cortex Tree

`core.hooksPath ~/.hermes-cortex/hooks` is global: the pre-commit/pre-push
hooks run in EVERY git repo on the host, including project repos (client-mwi,
client-works, and other client repos) that have no `ops/` tree and no `.hermes-cortex/`
directory inside them. Any hook/enforcer path built on `$REPO_ROOT` (the repo
being committed IN) and assuming cortex layout will break every commit there.

**Regression 2026-08-04 (`faa0e929` → fix `72d6cdc3`):** the adversarial gate
hard-resolved to `$REPO_ROOT/ops/scripts/quality/adversarial-verify.py` —
project repos lack that path, so ALL their commits failed fail-closed.
Fix pattern: candidate loop, repo-local first, then the canonically-deployed
copy at `$HOME/.hermes-cortex/scripts/` (registered by cortex-update.sh on
both Linux and macOS). Fail closed only if BOTH are missing. See
`enforcement-change-safety` Rule 6 for the full pattern and the 3-branch
verification (cortex repo / project repo / tool-missing).

When modifying hooks or the enforcer, test in a scratch project repo
(`git init /tmp/t && git config core.hooksPath ~/.hermes-cortex/hooks`)
before shipping — a cortex-repo-only test proves nothing about project repos.

## 2b. Deploy ≠ Load — Gateway Restart Required to Activate

`cortex-update.sh` copies the new enforcer to
`~/.hermes/plugins/governance-enforcer/` and re-locks it — but the RUNNING
gateway keeps executing the OLD module from memory. The plugin manager is a
process-global singleton: `hermes plugins disable/enable` only writes
`config.yaml`; it does NOT hot-reload loaded modules.

- **Symptom:** repo == deployed (SHA256 match) yet the sanctioned
  `bash ~/hermes-cortex/ops/scripts/cortex-update.sh --status` still returns
  `GOVERNANCE LOCK REQUIRED` → pending restart, not a code bug.
- **Fix:** `hermes gateway restart` — agents cannot run it (lifecycle guard);
  the host operator (Luke) must. Verify with the positive control (`--status`
  passes lock-free) and negative control (`... && echo hi` still blocked).
- **Don't:** re-run cortex-update.sh repeatedly, edit the deployed copy, or
  disable/enable the plugin to "reload" it — none of these activate the new
  code. Only a gateway restart does.

---

## 3. The Skills-Loaded Marker Race (FIXED — per-session files, 2026-08-01)

**The old design:** `.skills-loaded` at `~/.hermes-cortex/state/` was a single
file. ALL concurrent Hermes sessions wrote to it. When session B loaded skills,
it overwrote session A's marker. Session A's writes were then blocked because
`_check_skills_loaded_marker()` saw session B's ID.

**The fix:** per-session marker files at `~/.hermes-cortex/state/skills-loaded/<session_id>`,
plus per-session state at `state/skills-state/<session_id>.json`. Each session
writes and reads only its OWN files — concurrent sessions (telegram, cli 1,
cli 2 on one server) can never stomp each other. The daemon guard, subagent
guard, and sticky-marker-per-lock rules were removed; they're no longer needed.

**If your writes are blocked (marker missing or wrong content):**
```
cat ~/.hermes-cortex/state/skills-loaded/<your-session-id>
# → session:<your-session-id>  (valid)
# → empty / missing            (skills not loaded this session)
```

**Fix:**
1. Load all 8 always-section skills via `skill_view()` → your session's marker
   is auto-created
2. Write tools unblocked

**Legacy files:** the old `~/.hermes-cortex/state/.skills-loaded` and
`skills-state.json` files are inert — the enforcer no longer reads them. They
can be deleted once all sessions have restarted with the new enforcer.

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
- [ ] **Concurrent interactive sessions (multi-session):** session A and session B both load skills — neither blocks the other (regression test: `TestSkillsMarkerPerSession::test_second_session_does_not_invalidate_first`)
- [ ] **Cron session:** bootstrap creates its OWN marker without touching interactive sessions
- [ ] **Background session (`bg_`):** owns its own marker
- [ ] **Touch bypass closed:** empty/whitespace marker file → rejected
- [ ] **DOGFOOD sync:** deploy via `cortex-update.sh` — does `begin_change()` work?
- [ ] **Cross-machine pull:** another agent's enforcer commit arrives via pull — does DOGFOOD handle it?

**Quick test for per-session markers:**
```bash
echo "session:test" > ~/.hermes-cortex/state/skills-loaded/test-session
# Check: does _check_skills_loaded_marker("test-session") accept only exact content?
```

---

## References

- `plugins/governance-enforcer/__init__.py` — the enforcer itself
- `docs/orchestrator-only-paths.txt` — restricted paths
- `ops/scripts/pre-commit-score` — pre-commit hook with orchestrator guard
- `ops/scripts/manage/cortex_doctor/checks.py` — doctor checks (hook drift, enforcer permissions)
- `ops/scripts/cortex-update.sh` — deploy script with `deploy_governance_plugin()`
- `skills/devops/cortex-preflight/SKILL.md` — Pitfall 3 covers skills-loaded marker
