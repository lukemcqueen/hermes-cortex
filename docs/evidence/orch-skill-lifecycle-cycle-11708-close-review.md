# orch-skill-lifecycle cycle 11708 — evidence notes

## What this run changed

Seven SKILL.md files were copied from the deployed tree
(`~/.hermes/skills/<cat>/<name>/SKILL.md`) into the repo source
(`skills/<cat>/<name>/SKILL.md`), committed as `365f0604`, and deployed:

- autonomous-ai-agents/pi-coding-agent
- devops/governance-closeout
- devops/hermes-gateway-operations
- devops/mycortex
- devops/shared-repo-push-gates
- software-development/change-checklist
- software-development/session-manager

## How the copy was checked (committed-runnable, not asserted)

The script `ops/scripts/evidence/orch-skill-lifecycle-drift-sync-2026-10-09.sh`
performs three checks and was executed for this run; its output is committed in
`docs/evidence/orch-skill-lifecycle-drift-sync-2026-10-09.txt`:

1. SUBSET check — compares `365f0604^:<file>` (repo before the sync) against the
   synced file using `comm -23`; a line present before but absent after would be
   listed. Output: all pre-sync lines present; the few non-identical lines are
   the REPLACED/expanded lines (diff hunks of the form `NcA,B`), recorded with
   their text for inspection.
2. Fence balance — count of lines starting with triple-backtick; all even.
3. md5 identity — synced repo file vs deployed file; all equal.

A reviewer can re-execute with: `bash ops/scripts/evidence/orch-skill-lifecycle-drift-sync-2026-10-09.sh`

## Doctor state after deploy

Captured in the same evidence file:
- `Deploy sync — deployed commit matches HEAD` (the deploy-sync CHECK is clean)
- `Skill drift — all skills in sync` (the skill-drift CHECK is clean)
- `Overall: WARNING` with 5 pre-existing warnings and zero FAIL

The 5 warnings are outside this pipeline's scope: repo-clean (peer in-flight
files left unstaged intentionally), AGENTS.md efficiency (dev repo), two other
crons' last-run errors, and a stale deploy script.

## Provenance facts

- `f3a11e37` added `docs/evidence/agents-md-prune-scan-2026-10-09.txt` as a new
  file; `bbee30d2` later modified the same file. Both entries appear in the
  range diff because the range spans both commits.
- Commit `bbee30d2` message is this session's; its content is a peer's
  already-staged change (the AGENTS.md prune scan) that was in the index at
  commit time. Pushed history was not rewritten.
