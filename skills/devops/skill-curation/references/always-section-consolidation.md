# Always-Section Consolidation — 2026-08-20 (10 → 7)

Worked example of consolidating the `always:` section of the skills manifest.
Session: Esther, 2026-08-20. Commit `e1a035fa`.

## What was merged

| Absorbed skill | Survivor | Unique content preserved |
|---|---|---|
| `session-start-discipline` | `task-start` | todo-restore step (`task-db.py pending` → `todo()`), marker mechanics, known gaps; refs moved to `task-start/references/` |
| `reasoning-patterns` | `agent-flow` | full 4-pattern table + how-to-choose, embedded in "How to route" |
| `cortex-preflight` | `survey-before-action` | repo-specific pre-flight (git search, Hermes boundary, deploy verification), 5 deployment pitfalls |

`change-checklist` slimmed: Phase 0b → one-line reference to survey-before-action
Phase 0a; Phase 6 → one-line reference to reflexion-check.

`test-driven-development` was PROMOTED into the base gate (was already
demanded by the TDD co-gate for production-code writes).

## The four sources of truth (MUST stay in sync)

1. `docs/templates/skills.yaml` `always:` list (deployed `~/.hermes-cortex/skills.yaml`
   syncs from this template in cortex-update.sh)
2. `plugins/governance-enforcer/__init__.py`: `_REQUIRED_SKILLS` set,
   `_PATH_CTX_HINTS` (deploy/install → survey-before-action), the block-message
   numbered list (lines ~1690-1710), README "required skills" section
3. `ops/scripts/manage/cortex_doctor/checks.py`: `check_skills` `required` list
4. Docs: AGENTS.md RULE-1, CONTRIBUTING.md table, design docs
   (skills-session-manager-v2, task-workflow AC-10), ownership maps,
   supporting-skill-pattern, repo-health-review checklist

Pre-consolidation drift observed: enforcer=8, doctor=8, manifest=10,
session-start-discipline text=9. Four different counts for one gate.

## Merge mechanics that worked

- `aliases: [absorbed-name]` in the survivor's frontmatter — old references
  keep resolving (verified: skill_view by old name still finds the skill)
- Move `references/` files from absorbed → survivor BEFORE `git rm`
- Update the survivor's internal text that names the absorbed skill
  (Phase 0a table, recovery-from-violation list, related_skills)
- `hermes curator unpin <name>` before `skill_manage delete` (pinned refuse)
- `skill_manage delete` with `absorbed_into=<survivor>` for the deployed copy;
  `git rm -r skills/<cat>/<absorbed>` for the repo copy
- Regenerate `docs/SKILLS-MANIFEST.md` via `gen-skills-manifest.py` after

## Marker-invalidation trap

The enforcer's skills fingerprint = mtimes of the required skills' deployed
SKILL.md files. Deleting a deployed always-skill OR running cortex-update.sh
(re-syncs skills → mtimes change) invalidates YOUR OWN session marker. Every
write tool then blocks with "N/N always-section skills loaded" even though
you loaded everything; the block message still lists the OLD names because
the running gateway holds the old in-memory enforcer.

Fix: `skill_view()` a skill NOT yet loaded this session — a deduped reload
short-circuits and does NOT trigger the auto-create. A fresh name refreshes
the marker. May be needed twice: once after deleting deployed skills, once
after cortex-update.sh re-syncs them.

## Push/dogfood sequencing

Pre-push hook runs the doctor and blocks until deployed == repo
("Push blocked: doctor reports N failures"). Order that worked:

1. Commit (`git commit -F` with detailed message)
2. `bash ops/scripts/cortex-update.sh` (deploy)
3. Score and close the governance cycle (`cycle_query` → `feedback_accept` →
   `end_change`) — a PENDING cycle from a FINISHED task (no live lock, e.g. a
   sibling subagent that begin_change'd but never closed) is a doctor FAIL
   that blocks push; `feedback_accept` on it is legitimate cleanup, not a bypass
4. Doctor green (`cortex-doctor.py --quiet`, expect WARNING at most)
5. `git push` (pull --rebase first)

`end_change` releases the lock — open a fresh `begin_change` if you still
need terminal afterwards (e.g. for the push or final doctor run).

## Post-consolidation verification (all four must agree)

```bash
python3 -c "
import yaml, re
src = open('/home/esther/.hermes/plugins/governance-enforcer/__init__.py').read()
m = re.search(r'_REQUIRED_SKILLS: set = \{(.*?)\}', src, re.S)
enforcer = set(re.findall(r'\"([a-z-]+)\"', m.group(1)))
manifest = {s['name'] for s in yaml.safe_load(open('/home/esther/.hermes-cortex/skills.yaml'))['always']}
print('MATCH' if enforcer == manifest else f'DRIFT: {enforcer-manifest}, {manifest-enforcer}')
"
```

Also verify every always-skill has a deployed SKILL.md under `~/.hermes/skills/`
and the doctor's `Skills manifest: always` check passes.
