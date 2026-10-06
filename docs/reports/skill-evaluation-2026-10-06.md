# Skill Evaluation Report — orch-skill-evaluate

**Run:** 2026-10-06 (Tue) KST · cron `orch-skill-evaluate` (job `2da7ae15e810`)
**Evaluator:** Esther (orchestrator, hot standby)

## Phase 1 — Pending skill reports

**None.** `orch-skill-report-process.py` returns empty (exit 0). The staging dir
`~/.hermes-cortex/state/skill-reports/` holds 148 report parts (agents: esther,
gisu, joseph, kustos, titus), all at or older than the recorded processed
marker — i.e. every staged report has already been processed. No new fleet
report since late August.

## Phase 2 — Fleet skill inventory

**Defect found and fixed.** `orch-skill-evaluate.sh` enumerated only **36** of
**511** skills — `find … -maxdepth 2` missed every category-nested skill
(`security/*`, `finance/*`, `web/*`, …), under-reporting the inventory by ~93%.

Fixed in this run's 3 script commits (full-tree scan; `-d`/`-r` fail-loud
guards; temp-file stderr capture) and covered by the new
`test-orch-skill-evaluate.sh`. The deployed script now reports
`Total skills: 511`.

## Phase 3 — Evaluation decisions

| Skill | Status | Decision | Rationale |
|-------|--------|----------|-----------|
| `research/recurring-reports` | deployed newer than repo | **UPSTREAM** | Pure superset (verified `diff`: no repo-only lines). Adds chat-delivery guidance — final response *is* the delivered message; `MEDIA:` only for real files. Generic, useful. |
| `career-document-writing` | deployed newer than repo | **UPSTREAM** | Pure superset. Adds `.docx/.pdf/.md` deliverable section (render all three from one content definition). Generic, useful. |
| `brand-intelligence/skills/brand-brief` | deployed-only | **DEFER / do not upstream** | Calls external `sigai_*` MCP brand-intelligence tools. Vet checklist §2: external runtime service → not for the generic repo. Correct as a host/bundle skill; preserved (not deleted). |
| `brand-intelligence/skills/watchlist-digest` | deployed-only | **DEFER** | Same external-service dependency. |
| `brand-intelligence/skills/compare-brands` | deployed-only | **DEFER** | Same external-service dependency. |

## Phase 4 — Provenance of the audit range

Eight commits were in the push range. **This session authored the 2026-10-06
ones**, all touching only `ops/scripts/manage/orch-skill-evaluate.sh` (three
fix commits), its new test, and the two-skill upstream sync.

The remaining commits are **pre-existing prior-session work** — a
root-cause-debugging skill entry, a "sync 3 stranded deployed skills" commit,
and a bible-corpus-datasets trio — which this session only **rebased** so they
re-ran the pre-commit hook and cleared the `--no-verify` push gate. Their
content is unchanged and they were NOT evaluated as part of this run.

## Captured evidence

```
$ bash ops/scripts/manage/test-orch-skill-evaluate.sh
== 1. syntax ==
  PASS: bash -n clean
== 2. normal run enumerates skills (count > 0) ==
  PASS: Total skills: 511
== 3. missing skills root fails closed ==
  PASS: missing root -> exit 1 + ERROR
== 4. unreadable subdir emits find-error WARN ==
  PASS: unreadable subdir -> find-error WARN

RESULT: 4 passed, 0 failed
```

```
$ cortex-update.sh (skill lines)
✓   Skills: 0 updated, 383 unchanged
⚠   ⚠️  Deployed-only skill 'brand-brief' (brand-intelligence/skills/brand-brief) is not in the repo.
⚠   ⚠️  Deployed-only skill 'watchlist-digest' (brand-intelligence/skills/watchlist-digest) is not in the repo.
⚠   ⚠️  Deployed-only skill 'compare-brands' (brand-intelligence/skills/compare-brands) is not in the repo.
✓   Skills: 0 updated, 383 unchanged, 0 stale removed, 3 preserved (deployed-only, not auto-deleted)
  ✅ Skill drift
```

## Open blocker (out of scope, recorded as issue #57)

Push to origin is blocked by a pre-existing doctor FAIL `AGENTS.md (steadfaste)`
— the steadfaste repo's AGENTS.md mtime predates its HEAD commit, firing the
staleness check (`age_days < -1`). The remedy requires editing a **protected
agent-instruction file**, which the enforcer refuses in a non-interactive cron
(no approver). No bypass was used. Fix belongs to the next interactive esther
session (merge the B1/B2 Sandbox+Supervisor and Trust Execution Layer patterns
into the steadfaste AGENTS.md, commit through hooks).

## Result

- Inventory defect fixed + fail-loud guards + test: **3 script commits**
- Skills upstreamed: **2**
- Deployed-only skills evaluated: **3** (all DEFER — external service)
- Pending fleet reports: **0**
