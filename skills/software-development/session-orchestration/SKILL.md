---
name: session-orchestration
version: 1.0.0
category: software-development
description: >-
  Five-wave session orchestration: Discovery → Impl-Core → Impl-Polish →
  Quality → Finalization. Quality gates between each wave enforce
  handoff schemas, adversarial verification, and governance ledger entry.
pinned: true
related_skills:
  - change-checklist
  - adversarial-verifier
  - agent-contract
  - reasoning-patterns
---

# Session Orchestration — Five-Wave Delivery Pipeline

**Load this skill when starting a multi-wave task.**

Each wave is a typed phase with an input schema, an output schema, and a
quality gate that must pass before the next wave begins.

## Wave Map

```
Wave 1: Discovery   → Gate (audit findings, scope confirmed)
Wave 2: Impl-Core   → Gate (architecture review, core impl)
Wave 3: Impl-Polish → Gate (edge case review, error handling)
Wave 4: Quality     → Gate (simplify → test → adversarial verify)
Wave 5: Final       → Gate (verify specs → commit → governance ledger)
```

### Output Schema (per wave)

```yaml
wave_output:
  wave_name: str           # discovery | impl-core | impl-polish | quality | final
  correlation_id: str      # Ties to the bus EXEC that initiated this
  files_changed: str[]     # Files created/modified in this wave
  issues_found: int        # Issues found in this wave
  issues_fixed: int        # Issues resolved
  gates_passed: bool       # Did the quality gate pass?
  gate_output: str         # Summary of gate findings
  handoff_payload: str     # JSON schema-validated payload for next wave
  evidence_id: str?        # outerloop evidence ID (final wave only)
```

## Usage

### CLI: wave-orchestrate.py

```bash
# Start a new session through the 5 waves
wave-orchestrate.py start --task "Deploy auth service" --correlation-id exec-xyz

# Advance to next wave (runs quality gate)
wave-orchestrate.py advance --session <id>

# Check current wave status
wave-orchestrate.py status --session <id>

# Show quality gate results
wave-orchestrate.py gates --session <id>

# JSON output
wave-orchestrate.py status --session <id> --json
```

---

## Wave 1: Discovery

**Goal:** Understand the task, gather context, survey the problem space.

### Steps
1. Load relevant skills (survey-before-action, agent-flow, reasoning-patterns)
2. `search_files()` with 3+ terms for existing solutions
3. Audit the current state (what exists, what's missing)
4. Produce a scope document: files to change, approach, risks

### Gate: Audit Findings
- Scope must be documented
- Existing solutions must be surveyed (3+ search terms)
- Risks must be identified
- Approach must be chosen

### Output
- Scope document (as task description in governance)
- Audit findings
- Search results showing no existing solution to extend

---

## Wave 2: Impl-Core

**Goal:** Build the core implementation.

### Steps
1. `begin_change()` for governance
2. Create/modify core files
3. Core logic complete (happy path works)
4. Document what was built

### Gate: Architecture Review
- Code follows project conventions
- No dead code or speculative generality
- Error paths are handled
- Schemas are validated at boundaries

### Handoff to Wave 3
```bash
wave-orchestrate.py advance --session <id>
```

---

## Wave 3: Impl-Polish

**Goal:** Handle edge cases, improve error handling, add documentation.

### Steps
1. Review Wave 2 output for missing edge cases
2. Add error handling for failure modes
3. Add/update inline documentation
4. Verify with standard test suite

### Gate: Edge Case Review
- All explicit failure modes handled
- Empty/null/edge inputs tested
- Dependencies error paths covered
- Documentation written

### Handoff to Wave 4
```bash
wave-orchestrate.py advance --session <id>
```

---

## Wave 4: Quality

**Goal:** Adversarial verification + standard tests.

### Steps
1. Run standard test suite (tests must pass)
2. **Load `adversarial-verifier` skill**
3. Run adversarial verification with `--gate` mode:
   ```bash
   adversarial-verify.py --file <changed-files> --level A2 --gate
   ```
   `--gate` exits 0 if clean, 1 if critical/high findings block the release.
4. If findings: fix, re-run, loop
5. If clean: proceed

### Gate: Quality Check
- Standard test suite: 100% pass
- Adversarial verifier `--gate`: no critical/high findings
- All findings fixed or documented with rationale

### Adversarial Integration
```bash
# Gate mode — blocks release if critical/high findings exist
adversarial-verify.py --file ops/scripts/my-script.py --level A2 --gate
echo $?   # 0=pass, 1=blocked
```

### Pre-Commit Auto-Gate
The **pre-commit hook** automatically runs `adversarial-verify.py --gate` on
every staged `.py` file before allowing a commit. Critical/high findings
block the commit. Bypass with:
```bash
SKIP_ADVERSARIAL=1 git commit ...
```

### Handoff to Wave 5
```bash
wave-orchestrate.py advance --session <id>
```

---

## Wave 5: Finalization

**Goal:** Verify, commit, push, deploy, record in governance ledger.

### Steps
1. Verify all specs/acceptance criteria are met
2. Check: done checklist (cortex-doctor --quiet)
3. Commit and push
4. Deploy (cortex-update.sh --force-all)
5. **Run outerloop evidence → verdict cycle**
6. Score governance cycle

### Gate: Release Gate
```bash
# Pre-ship checklist
wave-orchestrate.py gates --session <id>

# Must pass all 6:
# 1. Arrays synced? (create vs uninstall)
# 2. Old thing removed?
# 3. Docs updated?
# 4. Syntax valid?
# 5. Doctor clean?
# 6. Pushed and deployed?
```

### Governance Integration
```bash
# Record evidence
outerloop evidence package \
  --run-id <session> \
  --passed <tests_passed> \
  --failed <tests_failed>

# Issue verdict
outerloop verdict issue \
  --evidence-id <id> \
  --decision ship \
  --rationale "All 5 waves passed"
```

---

## Quality Gate Reference

| Gate | Wave | Checks | Blocking? |
|------|------|--------|-----------|
| G1 | 1→2 | Scope surveyed, approach decided | Yes |
| G2 | 2→3 | Core impl complete, conventions followed | Yes |
| G3 | 3→4 | Edge cases handled, docs updated | Yes |
| G4 | 4→5 | Tests pass, adversarial clean | Yes |
| G5 | 5→done | Pre-ship checklist all pass | Yes |

### Automatic Rollback
If Wave 4 adversarial finds critical findings and they can't be fixed:
- Roll back to Wave 2 state
- Log to outerloop with `decision: block`
- Flag for human review

## Integration Points

| Component | Where |
|-----------|-------|
| **handoff_schema.py** (S2) | Validates WAVE_RESULT between waves |
| **adversarial-verify.py** (S3) | Wave 4 quality gate |
| **outerloop.py** (S4) | Wave 5 governance ledger |
| **fleet-audit.py** (S1) | Wave 1 discovery — check registry state |
| **fleet-costs.py** (F2) | Wave 5 — report costs in finalization |
| **change-checklist** | Pre-ship checklist in Wave 5 |

## Failure Recovery

| Failure | Recovery |
|---------|----------|
| Gate G1 fails (scope unclear) | Return to Wave 1, re-survey |
| Gate G2 fails (core broken) | Return to Wave 2, fix implementation |
| Gate G3 fails (buggy edge cases) | Return to Wave 3, fix edge cases |
| Gate G4 fails (adversarial findings) | Return to Wave 2 (critical) or Wave 3 (medium) |
| Gate G5 fails (pre-ship) | Fix blocker, re-verify gate |
