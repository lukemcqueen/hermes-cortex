# Repo Health Review — 2026-07-23

## Summary

A comprehensive audit of the Hermes Cortex repo: 168 scripts, 93 docs, 7 PRDs, 51 skill categories.
Audit focused on gaps, duplicates, naming inconsistencies, and consolidation opportunities.

**Findings: 16 issues total (7 fixed, 9 documented for future)**

---

## ✅ Fixed Issues (7)

### 1. Root-level test files moved to `tests/`
- `test-bus-failover.py` → `tests/test-bus-failover.py`
- `test-bus-schema.sh` → `tests/test-bus-schema.sh`
- `test-dashboard.sh` → `tests/test-dashboard.sh`

### 2. Stale caches removed
- Root `__pycache__/` (contained single stale `.pyc`) — deleted
- Root `.pytest_cache/` — deleted (regenerates on next run)

### 3. `inbox-flag.py` — triple duplicate pruned
- **Found:** 3 identical copies (`agent/`, `bus/`, `inbox/`) — all same MD5
- **Action:** Removed `agent/inbox-flag.py` and `bus/inbox-flag.py`
- **Kept:** `inbox/inbox-flag.py` (already the registered path in cortex-update.sh)

### 4. `remediation-sensor.py` — duplicate pruned
- **Found:** 2 copies (`manage/` and `health/`) with slightly different content
- **Action:** Removed `manage/remediation-sensor.py`
- **Kept:** `health/remediation-sensor.py` (newer, already registered in cortex-update.sh)

### 5. `offline_code_index_cron.sh` renamed to hyphen convention
- **Found:** Only script in `manage/` using underscore naming
- **Action:** Renamed → `offline-code-index-cron.sh`
- **No references found** — safe rename

### 6. PRD-005 v1 archived
- **Found:** Both v1 (300 lines) and v2 (434 lines) in `docs/prd/`
- **v2 supersedes v1** — v1 content completely absorbed into v2
- **Action:** Moved v1 → `docs/archive/PRD-005-enterprise-integration.md`
- **No docs reference v1** — safe archive

### 7. `.gitignore` confirmed healthy
- `__pycache__/` already gitignored
- `/runtime` symlink already gitignored
- All `*.db` already gitignored

---

## 🔍 Documented for Future Action (9)

### 8. PRD-002 (Delivery Harness) — no named implementation
- **Issue:** `docs/prd/PRD-002-delivery-harness.md` exists but no `delivery-harness`
  script, skill, or CLI exists
- **Status:** Parts absorbed into wave-orchestrate.py (Wave 5), outerloop.py,
  and change-checklist skill. PRD itself is stale as a standalone feature.
- **Suggestion:** Either mark as `superseded-by: wave-orchestrate + outerloop`
  or build the delivery harness

### 9. 26 docs not cross-referenced in any other doc
- PRDs are expected to be unreferenced (design docs, not linked from other docs)
- **Notable unreferenced docs with real content:**
  - `docs/cert-monitoring.md` (8KB) — useful cert monitoring guide, lost
  - `docs/model-tier-strategy.md` (5KB) — model tiering strategy, lost
  - `docs/linux-mint-migration.md` (4KB) — platform migration notes
  - `docs/loop-governance-reference.md` — governance reference, not linked
- **6 zero-byte files** in `docs/elicit/` — clearly stale meeting notes

### 10. `cortex-doctor.py` vs `cortex-health.sh` — adjacency
- **Found:** Both check system health
- Doctor (89KB): 40+ detailed checks, JSON output, per-service breakdown
- Health.sh (15KB): quick green/red overview, exits 0/1
- **Verdict:** Keep separate — different use cases (deep diagnostics vs quick smoke test)
- **Suggestion:** Could merge health.sh as `cortex-doctor --quick` flag

### 11. `run-evals.py` — standalone-execution gap
- **Issue:** Imports `hermes_tools` which only works inside a Hermes agent session
- Running from shell fails with `ModuleNotFoundError`
- **Suggestion:** Add a `--standalone` flag that bypasses hermes_tools import

### 12. `runtime` symlink → `core` — artifact
- `~/hermes-cortex/runtime → core/` — no scripts reference the symlink
- Already in `.gitignore` — harmless but unnecessary
- **Suggestion:** Remove if no external tooling depends on it

### 13. Learning/knowledge management pipeline — 7 scripts
- Scripts: `agent-learning-collector.py`, `daily-lesson-mine.sh`, `harvest-lessons.sh`,
  `lesson-compound-stats.py`, `lesson-hit.sh`, `process-skill-reports.py`,
  `send-agent-learning.sh`, `send-skill-report.py`, `skill-triage.py`
- **Observation:** Complex pipeline, but functional. No obvious duplication.
- **Suggestion:** Could consolidate into a `knowledge-pipeline.py` with subcommands

### 14. Health scripts — 18 scripts in `health/` + 1 in `manage/`
- Watchdogs, remediation, cert checks, memory checks, etc.
- **Observation:** Each watchdog is separate script (e.g., `agent-cron-quality-watchdog.py`,
  `model-health-watchdog.py`, `system-alert-watchdog.py`). Consolidating into
  a single `health-watchdog.py --type <check>` would reduce surface area but
  is a significant refactor.

### 15. 36 scripts not registered in cortex-update.sh
- Most are `install/` scripts (run once, not deployed), `agent/` scripts
  (per-agent, deployed differently), or `health/` watchdogs (deployed via
  cron definitions in install-crons.sh, not via cortex-update.sh)
- **Verdict:** This is expected — not all scripts need cortex-update.sh registration

### 16. Naming convention: strong consistency
- 55/57 scripts in `manage/` use hyphen naming ✅
- `quality/`, `hc/`, `lib/`, `install/` all use hyphens ✅
- Only `__pycache__` and the now-renamed `offline_code_index_cron.sh` used underscore
- **Verdict:** Good hygiene maintained

---

## Recommendations Priority

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| 🔴 High | PRD-002 supersession notice | 10 min | Docs clarity |
| 🔴 High | Cert-monitoring.md integration | 15 min | Security visibility |
| 🟡 Medium | `cortex-doctor --quick` merge | 1 hr | Reduced surface area |
| 🟡 Medium | run-evals.py standalone mode | 30 min | Better DX |
| 🟢 Low | runtime symlink removal | 5 min | Cleanliness |
| 🟢 Low | Zero-byte doc cleanup | 5 min | Reduce noise |
