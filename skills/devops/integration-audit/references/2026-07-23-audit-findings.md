# Integration Audit Session — 2026-07-23

## Context

Full S1-S4 fleet upgrade was built in a single session:
- S1: Agent Registry v4 (5 concerns) + `fleet-audit --level F1`
- S2: Handoff Schema Validation + `hc exec --output-schema`
- S3: Adversarial Verifier skill + CLI
- S4: Outerloop Governance (evidence → verdict → ledger → answerability)
- F2: Cost tracking + `fleet-audit --level F2`

Each system passed individual tests. The integration audit caught 3 gaps.

## Gap 1: Cheat Detection Regex

**System:** `adversarial-verify.py` — technique E (cheat detection)

**Bug:** The regex `except\s*(?:\w+\s*)*:\s*\n\s*(?:pass|...)` had `\s*` before
`\n`, which ate the newline character since `\s` in Python re matches `\n`.
Result: only `except:\n\n    pass\n` (two blank lines) would match.

**Fix:** Changed `:\s*\n` to `:[^\S\n]*\n` (non-newline whitespace only before
the newline). Also added a separate inline pattern for `except: pass` on one
line: `except\s*(?:\w+\s*)*:\s*pass\s*(?:#|$)`.

## Gap 2: fleet-audit --registry Path Fallback

**System:** `fleet-audit.py` — `find_registry()` function

**Bug:** When user passed `--registry /nonexistent`, `find_registry()` silently
fell back to auto-discovering the registry from standard locations
(`~/.hermes-cortex/state/`, repo example, etc.). The user's explicit path
was treated as a hint, not a requirement.

**Fix:** Added early `return None` when an explicit path doesn't exist, so
the caller prints an error instead of silently falling back.

**Principle:** Explicit user arguments should be followed, not treated as hints
with fallback to auto-discovery.

## Gap 3: Deployed Registry Drift

**System:** Fleet management — `agent-registry.json`

**Bug:** The repo file (`ops/install/deploy/agent-registry.json.example`) was
upgraded to v4, but the deployed runtime copy
(`~/.hermes-cortex/state/agent-registry.json`) was still v3. All toolchain
tests read the repo file, not the deployed copy.

**Fix:** Explicitly copied the v4 example to the deployed state path.

**Prevention:** Repo-to-deploy consistency check should be automatic. See
`integration-audit` skill Step 1.

## How the Audit Was Run

A 37-test Python script (`integration-audit.py`, removed after use) tested:
- S1: Registry structure, fleet-audit at F0/F1/F2, missing file, template fails
- S2: All 5 schemas, valid/invalid payloads per schema, hc exec help
- S3: A1/A2 runs on real files, cheat detection, JSON output, edge cases
- S4: Evidence creation, verdict issuance, answerability, error cases
- F2: DB connectivity, fleet-costs summary/weekly/jobs
- Integration: cross-system composition, deployed state, help output

## Key Lessons

1. **Test the deployed path, not just the repo path.** Tools that read from
   `ops/install/deploy/` in tests may mask stale runtime copies.
2. **Test error paths explicitly.** The `--registry /missing` fallback was
   only visible when a user actually made a typo.
3. **Regex with `\s*` before `\n` is a bug pattern.** Always use `[^\S\n]`
   (whitespace without newline) before literal `\n` anchors.
4. **Individual system tests pass; integration tests fail.** A system that
   works in isolation may not compose with its consumers.
