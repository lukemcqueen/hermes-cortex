---
name: integration-audit
version: 1.0.0
category: devops
description: >-
  Comprehensive integration audit — runs all changed subsystems together
  before final commit to catch cross-system gaps that individual testing
  misses. Covers registry validation, schema checks, cheat detection,
  deployed-state drift, doctor, and syntax verification.
pinned: true
related_skills:
  - cortex-preflight
  - change-checklist
  - fleet-management
  - adversarial-verifier
---

# Integration Audit — Pre-Commit Cross-System Validation

## When to Use

Before every `end_change()` call when the session touched multiple systems,
or when a single change cascades across files, configs, and data stores.

**Signals that an integration audit is needed:**
- Multiple systems modified (registry + schemas + scripts + docs)
- Change touches both producers and consumers of data (e.g., schema + validator)
- You modified a tool and its consumers in the same session
- Stateful data was updated (registries, DBs, config files that persist across sessions)

## The Protocol

Do NOT test each system independently — that misses cross-system gaps.
Test them together in sequence, feeding each system's output into the next.

**References in this skill:**
- `references/cheat-patterns.md` — regex signatures for all known cheat patterns
- `references/wave-orchestration-quickref.md` — wave orchestration CLI reference
- `references/2026-07-23-audit-findings.md` — real audit findings from this session

### Step 1: Verify Repo-to-Deploy Consistency

Before running any tool, check that the deployed state matches the repo:

```bash
# Check deployed registry vs repo (common drift source)
diff ~/.hermes-cortex/state/agent-registry.json \
     ~/hermes-cortex/ops/install/deploy/agent-registry.json.example \
     2>/dev/null || echo "⚠️  Registry drift detected"

# Check any other state files that might be stale
```

**Failure pattern from 2026-07-23:** Deployed `agent-registry.json` was still
v3 while the repo had v4. All toolchain tests passed individually because they
read the repo example file, not the deployed state.

### Step 2: Run Fleet Audit (if registry changed)

```bash
fleet-audit --level F1
```

If F2 scope: `fleet-audit --level F2`

Exit must be 0. Non-zero means the registry has validation failures that
will affect all downstream consumers.

### Step 3: Validate Handoff Schemas (if schemas changed)

```bash
python3 -c "
from handoff_schema import validate_payload as v
# Test EXEC
ok, _ = v({'command':'test.py','timeout':30}, 'EXEC')
assert ok, 'EXEC schema invalid'
# Test EXEC_RESULT
ok, _ = v({'command':'t.sh','exit_code':0,'success':True}, 'EXEC_RESULT')
assert ok, 'EXEC_RESULT schema invalid'
# Test WAVE_RESULT
ok, _ = v({'wave_name':'a','agents':[{'agent':'e','success':True,'exit_code':0}],'all_passed':True}, 'WAVE_RESULT')
assert ok, 'WAVE_RESULT schema invalid'
# Test UPDATE_REQUEST
ok, _ = v({'target_sha':'abc1234','run_doctor':True}, 'UPDATE_REQUEST')
assert ok, 'UPDATE_REQUEST schema invalid'
print('All schemas valid')
"
```

### Step 4: Run Adversarial Verification (on any changed code)

```bash
adversarial-verify.py --file <path-to-changed-file> --level A2
```

Critical/high findings block the release. Medium/low findings must be fixed
or documented before release.

See `references/cheat-patterns.md` for known cheat patterns, regex
signatures, and the `\s*\n` pitfall to avoid when writing detection rules.

### Step 5: Test Outerloop (if governance changed)

```bash
# Create evidence package
outerloop evidence package --run-id "integ-test-$(date +%s)" \
  --passed 1 --json > /tmp/_ol_test.json

# Extract evidence ID
EID=$(python3 -c "import json; print(json.load(open('/tmp/_ol_test.json'))['evidence_id'])")

# Issue verdict
outerloop verdict issue --evidence-id $EID --decision ship \
  --rationale "Integration audit test" --by auditor

# Verify answerability
outerloop ledger why $EID | grep -q "Verclict\|Verdict" || echo "⚠️  Answerability chain incomplete"

# Clean up test evidence
rm -f /tmp/_ol_test.json
```

### Step 6: Run Doctor

```bash
cortex-doctor.py --quiet
```

Exit must be 0. Any FAIL introduced by your change must be fixed before
`end_change()`. If the FAIL is pre-existing, document it.

### Step 7: Syntax Verification

```bash
# Shell scripts
bash -n <every-changed-.sh-file>
# Python scripts
python3 -m py_compile <every-changed-.py-file>
# YAML
python3 -c "import yaml; yaml.safe_load(open('<file>'))"  # if applicable
```

### Step 8: Vote

| Result | Action |
|--------|--------|
| All steps pass (0 failures) | ✅ Safe to call `end_change()` |
| Critical/high adversarial finding | 🔴 Fix before release |
| Medium/low adversarial finding | Fix or document in feedback note |
| Doctor FAIL (new) | 🔴 Fix root cause |
| Doctor FAIL (pre-existing) | Document in feedback note |
| Registry drift | 🔴 Deploy or revert |
| Schema invalid | 🔴 Fix before release |

## What "Pass" Means

Every step must produce evidence you can cite. "It felt right" is not evidence.
For each step, you should be able to say:

- `fleet-audit --level F1` exited 0 with N agents passing
- Schema validation printed "All schemas valid"
- `adversarial-verify` found 0 critical/high findings
- `outerloop` full cycle completed without errors
- `cortex-doctor --quiet` exited 0
- `bash -n` and `py_compile` produced no errors

## Real Example (2026-07-23)

During the S1-S4 build, an integration audit caught 3 cross-system gaps
that individual system testing missed:

1. **Cheat detection regex** — only matched multi-line `except:\n    pass`,
   missed single-line `except: pass`. Fixed with inline pattern.
2. **fleet-audit --registry path** — silently fell back to auto-discovered
   registry when user specified a non-existent path. Fixed by returning None
   for explicit paths that don't exist.
3. **Deployed registry drift** — `~/.hermes-cortex/state/agent-registry.json`
   was still v3 while repo had v4. Copied v4 example to runtime path.

All three were invisible to individual system tests. Only the integration audit
exercised the real end-to-end path.

## Anti-Patterns

| Anti-pattern | Why It's Wrong |
|-------------|----------------|
| Testing each system in isolation | Misses cross-system gaps |
| Testing against repo files, not deployed state | Deployed state may be stale |
| Skipping steps because "it's a small change" | Small changes cause production failures too |
| Running audit only when asked | Make it automatic before every end_change |
| Not cleaning up test artifacts | Test evidence packages clutter the real ledger |
