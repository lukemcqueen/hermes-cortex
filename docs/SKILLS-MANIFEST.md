# Skills Manifest — Hermes Cortex

Skills ported from AgentKore (`ak-` prefix → `hc-` prefix) and developed
natively. All 9 skills live under `skills/software-development/<name>/SKILL.md`
and auto-install via `install.sh` step 10.

## Planning Pipeline

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `hc-elicit` | 1.1.0 | Requirements elicitation — deep/fast modes, RICE/MoSCoW prioritization, domain question banks | `skill_view(name='hc-elicit')` |
| `hc-party` | 1.1.0 | Multi-role architecture review — 6 roles, weighted decision matrix, conflict resolution, cost estimates | `skill_view(name='hc-party')` |
| `story-slicing` | 1.0.0 | Break features into user-visible, testable stories with INVEST checklist | `skill_view(name='story-slicing')` |
| `prd-lite` | 1.0.0 | Concise 1-page PRD template — 14 sections, clear scope, acceptance criteria | `skill_view(name='prd-lite')` |

## Execution Methodology

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `agent-flow` | 1.0.0 | Workflow router — 12 patterns (simple code, enterprise, debug, UI, API, DB, etc.) | `skill_view(name='agent-flow')` |
| `agent-contract` | 1.0.0 | Non-negotiable execution rules — real work, verified results, no simulation | `skill_view(name='agent-contract')` |
| `change-test-loop` | 1.0.0 | Test-first with confidence scoring (3/2/1/0), bounded retries (max 2), fallback | `skill_view(name='change-test-loop')` |
| `session-manager` | 1.0.0 | Session checkpoint/restore, context compression, progress tracking | `skill_view(name='session-manager')` |
| `state-orchestrator` | 1.0.0 | Info routing decision matrix — live context vs session vs memory vs docs | `skill_view(name='state-orchestrator')` |

## Naming Convention

Skills ported from AgentKore were renamed from `ak-*` to `hc-*`:
- `ak-elicit` → `hc-elicit`
- `ak-party` → `hc-party`

All cross-references in other skills have been updated. No stale `ak-`
references remain.

## Version History

| Date | Change |
|------|--------|
| 2026-06-08 | Initial manifest — 9 skills ported from AgentKore |
