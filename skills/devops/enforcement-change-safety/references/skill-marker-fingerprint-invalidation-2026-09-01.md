# Skill-Marker Fingerprint Invalidation — the "7/7 loaded ✅ but blocked" loop (2026-09-01)

Incident trace: fixing the always-skill list drift (AGENTS.md Rule 1) caused the
session's own marker to go stale THREE times in one pass. This is the failure
mode behind Luke's report: "the enforcer requires test-driven-development as one
of the 7 — it wasn't in the manifest's always list I loaded."

## The mechanism

The per-session marker (`~/.hermes-cortex/state/skills-loaded/<session_id>`) is
`session:{id}|skills:{fingerprint}`, where the fingerprint is an md5 of the
**mtimes of the 7 always-skill SKILL.md files** (`_skills_fingerprint()`,
Rule 14d). Consequences:

1. **ANY deploy that touches a skill file changes the fingerprint.** That means
   `cortex-update.sh` AND the mandatory dogfood deploy inside `git push` (Rule 12)
   — pushing a skill/docs change re-deploys the skills and invalidates EVERY
   session's marker, including the session doing the pushing.
2. The auto-create fires on `skill_view` ONLY when the in-memory per-session
   loaded-set (`_session_skills_loaded[session_id]`) already contains all 7.
   That set lives in the GATEWAY PROCESS — a gateway restart (or host reboot)
   empties it.
3. Result: "7/7 always-section skills loaded ✅" in the block message AND the
   write still blocked. The ✅ reflects the current load; the block reflects the
   stale marker. Not a contradiction — two different state pieces.

## Recovery (both paths)

- **Gateway NOT restarted since the skills were loaded** (in-memory set intact):
  ONE serial `skill_view(name='<any-always-skill>')` re-triggers the auto-create
  with the new fingerprint. (Batching several skill_view calls in one turn does
  NOT trigger it reliably — the trigger is the per-call hook.)
- **Gateway/host restarted** (in-memory set empty): must re-load ALL 7
  always-skills via `skill_view()` — they are read-only, so the gate does not
  block them; the 7th call regenerates the marker with the new fingerprint.

This bit a real session 3× in ~40 min: initial `cortex-update.sh`, then the
dogfood deploy inside the first (raced) push, then again after the successful
push's dogfood. Expect it whenever your change touches skills/ or AGENTS.md.

## The docs-drift variant (what Luke actually hit)

The enforcer's `_REQUIRED_SKILLS` comment says it "MUST stay in sync with
docs/templates/skills.yaml `always:` and doctor checks.py" — but it missed a
fourth sync point: **AGENTS.md Rule 1**, which enumerated the always-set with
pre-2026-08-20 names (`reasoning-patterns`, `cortex-preflight`) and omitted
`test-driven-development`. Sessions loading per Rule 1 loaded the wrong set and
failed the marker. Fix was a one-line list replacement; also greps for the
stale class found `"8 always-skills"` leftovers in three skill bodies (the set
is 7 since the 2026-08-20 consolidation).

**Lesson: when the always-skill set changes (add/remove/rename), grep the WHOLE
repo for enumerations of it** — enforcer `_REQUIRED_SKILLS`, the two
skills.yaml files, doctor checks.py, AGENTS.md, and any `N always-skills` prose
in skill bodies. The enforcer's own comment names three; AGENTS.md was the
fourth that bit us.

## Related

- Rule 14d — `_skills_dir()` resolution + fingerprint mechanism.
- `task-start` SKILL.md "Marker mechanics" — now documents both recovery paths
  (updated 2026-09-01).
