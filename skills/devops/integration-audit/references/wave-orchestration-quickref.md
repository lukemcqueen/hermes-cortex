# Wave Orchestration Quick Reference

CLI usage for the 5-wave delivery pipeline.

## Commands

| Command | Purpose |
|---------|---------|
| `wave-orchestrate.py start --task "Deploy X"` | Start a new session in Wave 1 (Discovery) |
| `wave-orchestrate.py advance --session <id> --passed` | Advance to next wave (runs quality gate) |
| `wave-orchestrate.py status --session <id>` | Show current wave + gate history |
| `wave-orchestrate.py gates --session <id>` | Show detailed gate check results |
| `wave-orchestrate.py list` | List all sessions (active + complete) |

## Quality Gates

| Gate | From | To | Key Checks |
|------|------|----|------------|
| G1 | Discovery | Impl-Core | Scope surveyed, 3+ search terms, risks identified |
| G2 | Impl-Core | Impl-Polish | Syntax valid, conventions, error paths, schemas |
| G3 | Impl-Polish | Quality | Edge cases, deps failures, docs, tests pass |
| G4 | Quality | Final | Tests 100%, adversarial no crit/high findings |
| G5 | Final | Complete | Arrays synced, old removed, docs, doctor, push+deploy |

## Integration Points

- **Wave 4** → `adversarial-verify.py --level A2` (adversarial verification)
- **Wave 5** → `outerloop.py` evidence package (governance ledger)
- **Wave 5** → `fleet-costs.py` (cost tracking in finalization)

## Example: Full Cycle

```bash
# Start
wave-orchestrate.py start --task "Fix auth service" --correlation-id exec-abc123

# Advance through gates
wave-orchestrate.py advance --session <id> --passed --checks scope surveyed risks approach
wave-orchestrate.py advance --session <id> --passed --checks syntax conventions error_paths schemas
wave-orchestrate.py advance --session <id> --passed --checks edge_cases deps_failures docs_updated tests_pass
wave-orchestrate.py advance --session <id> --passed --checks tests_pass adversarial_check fix_or_doc
wave-orchestrate.py advance --session <id> --passed --evidence "All checks passed, committed abc123"

# Check full status
wave-orchestrate.py status --session <id>
```

## DB

State stored in `~/.hermes-cortex/state/wave-sessions.db` (SQLite WAL).
Tables: `sessions`, `gate_results`, `wave_outputs`.
