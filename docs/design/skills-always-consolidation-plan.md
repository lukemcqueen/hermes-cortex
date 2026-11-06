# Skills Always-Section Consolidation — 8 → 3 (PLAN, 2026-11-06)

> Operator decision (2026-11-06): consolidate the `always:` skills from 8 to 3,
> split along the agent's lifecycle (route → execute → verify). Engage the
> governed deepseek-pro reviewer before building; land the enforcement as a
> SINGLE SOURCE OF TRUTH so the count can never drift again (the direct cause of
> the 7-vs-8 discrepancy the operator hit).

## The 3 consolidated skills

| # | New name | Absorbs | aliases (so old refs keep resolving) |
|---|---|---|---|
| 1 | `task-orient` | `task-start`, `agent-flow` | `task-start`, `agent-flow` |
| 2 | `execute-right` | `agent-contract`, `survey-before-action`, `prove-before-create`, `test-driven-development` | `agent-contract`, `survey-before-action`, `prove-before-create`, `test-driven-development` |
| 3 | `verify-and-ship` | `change-checklist`, `reflexion-check` | `change-checklist`, `reflexion-check` |

Lifecycle rationale: an agent routes (1), does real work (2), and verifies
before shipping (3). Each new skill is the consolidation of disciplines that
pointer-chase each other today (`change-checklist` says "run reflexion-check",
`task-start` bundles the sequence, `survey-before-action` and
`prove-before-create` overlap on "extend, don't rebuild"). Merging removes the
cross-reference layer AND duplicate prose — the merge is also a trim.

## Design centerpiece — SINGLE SOURCE OF TRUTH

Today the always-set exists in FIVE places that drift. The fix: **`skills.yaml`
`always:` is the only place the set is declared.** Both the enforcer and the
doctor DERIVE the required set from it instead of hardcoding a second list.

- `plugins/governance-enforcer/__init__.py:83` `_REQUIRED_SKILLS` becomes a
  lazy read of DEPLOYED `~/.steadfaste-fleet/skills.yaml` `always:` names (the
  same file the cron bootstrap at line 3119 already reads), with a documented
  fail-closed fallback constant for remote backends where the path is not
  mounted (README:561 case).
- `ops/scripts/manage/fleet_doctor/checks.py:966-972` `required` list becomes
  self-consistent: compare deployed `always:` against the repo template's and
  check each declared name has a loadable SKILL.md — no hardcoded N-list.
- The gate predicate (`__init__.py:305 _session_skills_loaded[...] >=
  _REQUIRED_SKILLS`) stays; it just measures the derived set.
- Hardcoded count strings (`"N/7"`, `"Load all 7"`, `"the 7th one"`, "Canonical
  7"; lines ~3314-3355, 78; README 240, 252, 281-285) become dynamic via
  `len(required)` or the named list.

Net: the next consolidation changes ONE file and everything follows. Durable,
not just today's count.

## Reference surface (file:function:line)

**Declarations:** `skills.yaml` `always:` 8→3; deployed
`~/.steadfaste-fleet/skills.yaml` syncs via fleet-update.sh.

**Enforcer (repo `plugins/governance-enforcer/` + deployed `~/.hermes/plugins/`):**
- `__init__.py:83` `_REQUIRED_SKILLS` derive from skills.yaml
- `__init__.py:78` "Canonical 7" comment — update
- `__init__.py:305` `>= _REQUIRED_SKILLS` — unchanged
- `__init__.py:3314-3355` `"/7"`/`"Load all 7"`/numbered list — dynamic
- `__init__.py:3110-3138` cron bootstrap — already reads skills.yaml, verify
- `README.md:240,252,281-285` "7 required" — update to 3

**Doctor:** `ops/scripts/manage/fleet_doctor/checks.py:931-1000` `check_skills`
derive required from template `always:`, self-consistent; update comment :966.

**Pre-commit ritual gate (names skills — the wire that actually binds):**
- `ops/scripts/pre-commit-score:908` `for _ritual_skill in reflexion-check
  survey-before-action prove-before-create agent-contract` — remap to the 3 new
  names. `hc-reflexion-check --skill <name>` answers from the tool-event store
  keyed by the name passed to skill_view, so the loop MUST name the new skills
  (aliases do NOT satisfy it).
- `ops/scripts/hc-reflexion-check.py:47` `DEFAULT_SKILL="reflexion-check"` — the
  verify survivor (`verify-and-ship`).

**Tests:**
- `tests/test_plan_review_gate.py:181` asserts `"prove-before-create" in
  enf._REQUIRED_SKILLS` — REWRITE to assert derivation (always-set comes from
  skills.yaml; every name is loadable). This pins exactly the drift bug.
- `tests/test_audit_pi_curated_set.py:37,100-102` names `prove-before-create` —
  update to the survivor.

**Docs:** `docs/SKILLS-MANIFEST.md` regenerate via `gen-skills-manifest.py`;
AGENTS.md RULE-1 banner; CONTRIBUTING.md table; ownership maps; design docs
that list the always-set.

**skill-curation mechanics** (`references/always-section-consolidation.md`):
survivor gets `aliases:`; move surviving `references/` to survivor; unpin before
delete; delete with `absorbed_into`; regenerate manifest. **Marker-invalidation
trap:** deleting deployed always-skills + fleet-update invalidate the running
session's marker and the block message names OLD names until gateway reload;
after content deploy, `skill_view` a fresh name to refresh (may need twice).

## Options rejected

- **Drop to 7** (remove `prove-before-create`): keeps multi-source drift AND the
  larger always-load; the discipline already lives in `survey-before-action`.
- **Fix strings 7→8, keep 8:** cosmetic; leaves the drifted five-source model.
- **Keep one file per discipline, only change count:** misses the lifecycle
  consolidation the operator asked for.

## Slicing into governed cycles

1. **THIS cycle — plan + pro review.** Commits this doc + the recorded
   `adversarial_reviews` row + evidence. No build.

   **Pro review 2026-11-06:** submitted via
   `ops/scripts/orch-bus/adversarial-review.py --cycle-id 14197 --review
   --reviewer-id esther-plan-review`, reviewer model
   `deepseek/deepseek-v4-pro-0813`. Verdict **CLEAN**, 0 findings, recorded in
   `adversarial_reviews` (`loop-governance.db`, cycle_id=14197). Per the
   plan-review rule, CLEAN validates the plan's claims, not its predicted
   consequences — the build cycle's RED tests falsify those.
2. **Build cycle — content first, count second, atomically in ONE push**
   (skills.yaml↔enforcer/doctor must never disagree mid-fleet): write the 3 new
   skills (repo + deployed), mark 8 absorbed, set `skills.yaml always:`. → 3,
   rewire enforcer/doctor/ritual-loop/DEFAULT_SKILL/tests/AGENTS/README/manifest,
   verify TDD + doctor + adversarial gate, deploy, push.
3. **Fleet convergence** — deployed gate converges host-by-host on next update.

## Risks

- **Gateway holds in-memory enforcer until restart** — after deploy, block
  message may list old names until a fresh session; marker may need a refresh
  `skill_view`. Expected.
- **Aliases don't satisfy `hc-reflexion-check --skill`** — why the ritual loop
  and DEFAULT_SKILL get NEW names and tests assert the new invariant.
- **Remote backends without `~/.steadfaste-fleet`** — lazy derivation needs the
  documented fail-closed fallback.