# Skills Manifest — Hermes Cortex

Skills in this repo auto-install via `install.sh` step 10, which
recursively copies `skills/` to `~/.hermes/skills/`, preserving category
subdirectories. Skills are distributed across multiple categories matching
their domain.

## Software Development (19 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `hc-elicit` | 1.1.0 | Requirements elicitation — deep/fast modes, RICE/MoSCoW, domain question banks | `skill_view(name='hc-elicit')` |
| `hc-party` | 1.1.0 | Multi-role architecture review — 6 roles, weighted decision matrix | `skill_view(name='hc-party')` |
| `story-slicing` | 1.0.0 | Break features into user-visible, testable stories with INVEST | `skill_view(name='story-slicing')` |
| `prd-lite` | 1.0.0 | Concise 1-page PRD template — 14 sections | `skill_view(name='prd-lite')` |
| `agent-flow` | 1.0.0 | Workflow router — 12 patterns (simple code, enterprise, debug, etc.) | `skill_view(name='agent-flow')` |
| `agent-contract` | 1.0.0 | Non-negotiable execution rules — real work, no simulation | `skill_view(name='agent-contract')` |
| `plan` | 2.1.0 | Plan mode — write actionable markdown plans, no execution | `skill_view(name='plan')` |
| `change-test-loop` | 1.1.0 | RED-GREEN-REFACTOR with confidence scoring, retry limits, coverage requirements, and strict TDD discipline | `skill_view(name='change-test-loop')` |
| `public-contribution` | 1.0.0 | After any improvement, evaluate whether it's public-worthy for the Hermes Cortex OSS community, genericize, and contribute | `skill_view(name='public-contribution')` |
| `session-manager` | 1.0.0 | Session checkpoint/restore, context compression, progress tracking | `skill_view(name='session-manager')` |
| `state-orchestrator` | 1.0.0 | Info routing — live context vs session vs memory vs docs | `skill_view(name='state-orchestrator')` |
| `skill-from-lesson` | 1.0.0 | Turn bugs, corrections, and discoveries into durable skills — decision tree, workflow, pitfalls | `skill_view(name='skill-from-lesson')` |
| `subagent-driven-development` | 1.0.0 | Execute plans via delegate_task subagents (2-stage review) | `skill_view(name='subagent-driven-development')` |
| `systematic-debugging` | 1.0.0 | 4-phase root cause debugging | `skill_view(name='systematic-debugging')` |
| `requesting-code-review` | 1.0.0 | Pre-commit review: security scan, quality gates, auto-fix | `skill_view(name='requesting-code-review')` |
| `spike` | 1.0.0 | Throwaway experiments to validate ideas before build | `skill_view(name='spike')` |
| `memory-architecture` | 1.0.0 | Agent memory system — MEMORY.md structure, privacy, gitignore | `skill_view(name='memory-architecture')` |
| `ecosystem-audit` | 1.0.0 | Evaluate third-party tools for adoption, integration, or removal | `skill_view(name='ecosystem-audit')` |
| `documentation-maintenance-audit` | 1.0.0 | Survey docs vs implementation, fix gaps systematically | `skill_view(name='documentation-maintenance-audit')` |

## DevOps (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `nginx-web-app-deployment` | 1.0.0 | Deploy web apps behind nginx — upstream config, SSL, rate limiting, launchd/systemd, multi-layer testing | `skill_view(name='nginx-web-app-deployment')` |

## Social Media

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `client-brand-brand-marketing` | 1.0.0 | Full brand marketing for The Client Brand (@client-brand.co) — sustainable fashion bags, faith-driven, voice strategy, social media, content calendars, copy templates, email sequences, product storytelling | `skill_view(name='client-brand-brand-marketing')` |

## Productivity

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `korean-language-learning` | 1.0.0 | Warm Korean language companion for English speakers 50+ — Hangul, grammar, honorifics, pronunciation, Anki strategies, reading progression, cultural context, conversation scripts | `skill_view(name='korean-language-learning')` |

## Naming Convention

Skills ported from AgentKore were renamed from `ak-*` to `hc-*`:
- `ak-elicit` → `hc-elicit`
- `ak-party` → `hc-party`

All cross-references in other skills have been updated. No stale `ak-`
references remain.

## Notes

- **`test-driven-development`** and **`writing-plans`** have been merged into
  `change-test-loop` (v1.1.0) and `plan` (v2.1.0) respectively — they are no
  longer standalone skills.
- All skills within a category share consistent tooling conventions.

## Version History

| Date | Change |
|------|--------|
| 2026-06-08 | Initial manifest — 9 skills ported from AgentKore |
| 2026-06-11 | TDD merged into change-test-loop (v1.1.0), writing-plans merged into plan (v2.1.0) |
| 2026-06-09 | Added public-contribution, skill-from-lesson (software-development), nginx-web-app-deployment (devops), SOUL.md template, updated nginx template |
