# Doctor Severity Philosophy — Identity Documents Are Non-Negotiable

> Captured 2026-07-25 after correction: "Soul is not advisory!" and "Agents is important!"
> The doctor's severity levels encode a trust model — what's OK to drift and what isn't.

## The Hierarchy

| Severity | Meaning | Use For |
|----------|---------|---------|
| ❌ FAIL | Blocks the overall result. Must be resolved before end_change. | Identity documents, security, governance, deploy integrity |
| ⚠️ WARN | Not ideal but non-blocking. Should be addressed when possible. | Optimization targets (size >15K), performance hints, optional features |
| ℹ️ INFO | Observation, not a problem. | Pre-existing conditions, contextual data |
| ✅ PASS | Verified correct. | Everything that checks out |

## The Lesson (2026-07-25)

I refactored the SOUL.md sync check and incorrectly changed it from FAIL to WARN with this rationale:

> *"Local ~/.hermes/SOUL.md is the agent's own identity document, not a repo-managed file. Template drift is advisory."*

**User's response:** *"Soul is not advisory!"*

And when I left AGENTS.md at WARN: *"Agents is important!"*

## What Makes a Check FAIL vs WARN

**FAIL criteria** — any of these is sufficient:
1. **Identity drift** — SOUL.md, AGENTS.md, or any agent's self-description document is out of sync with the template. These define who the agent is and how it operates — drift means the agent has wrong instructions.
2. **Security bypass** — hooksPath is unset, dangling symlinks, governance lock missing
3. **Deploy integrity** — deployed copy doesn't match repo source (hooks, scripts, plugins)
4. **Governance violation** — score-cycle blocked, pre-commit rejected

**WARN criteria:**
1. **Optimization** — SOUL.md >15K (could be trimmed but isn't wrong)
2. **Deprecation** — legacy naming conventions, superseded formats
3. **Deferred** — orphan crons known to the user, stale locks from active sessions

## When Refactoring Doctor Checks

**Preserve the severity when restructuring.** If the original check was FAIL and you're moving it to a new location or format, keep FAIL. The original author chose FAIL for a reason. If you think the severity should change, validate with the user before committing — don't downgrade silently.

**User's exact words (2026-07-25):** *"Don't lose the detailed checks for the templates!"* — meaning the marker comparison logic AND its FAIL severity must be preserved.

## Cross-Reference

- `self-improvement-pipeline` Tenet 2: "Doctor warnings are blocking failures — NOT optional"
- `self-improvement-pipeline` Tenet 7: "Template is the single source of truth"
- cortex-doctor.py: `check_soul_sync()` — FAIL on marker mismatch, FAIL on size >20K, WARN on size >15K
- cortex-doctor.py: AGENTS.md sync is FAIL on missing or content mismatch
