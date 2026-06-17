# Skills Manifest — Hermes Cortex

Skills in this repo auto-install via `install.sh` step 10, which
recursively copies `src/skills/` to `~/.hermes/skills/`, preserving category
subdirectories. Skills are distributed across multiple categories matching
their domain.

## GitHub (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `pr-review` | 1.0.0 | Full PR review pipeline — whole-repo context, architecture analysis, lesson-DB pattern matching, test regression check, and formal review with inline comments. Zero external API costs. | `skill_view(name='pr-review')` |

## Software Development (19 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `hc-elicit` | 1.1.0 | Requirements elicitation — deep/fast modes, RICE/MoSCoW, domain question banks | `skill_view(name='hc-elicit')` |
| `hc-party` | 1.1.0 | Multi-role architecture review — 6 roles, weighted decision matrix | `skill_view(name='hc-party')` |
| `story-slicing` | 1.0.0 | Break features into user-visible, testable stories with INVEST | `skill_view(name='story-slicing')` |
| `prd-lite` | 1.0.0 | Concise 1-page PRD template — 14 sections | `skill_view(name='prd-lite')` |
| `agent-flow` | 1.0.0 | Workflow router — 12 patterns (simple code, enterprise, debug, etc.) | `skill_view(name='agent-flow')` |
| `agent-contract` | 1.0.0 | Non-negotiable execution rules — real work, no simulation | `skill_view(name='agent-contract')` |
| `agent-inbox` | 1.0.0 | Web-based agent messaging system — topic channels, thread support, priority field, JSON API for agent-to-agent communication. | `skill_view(name='agent-inbox')` |
| `plan` | 2.1.0 | Plan mode — write actionable markdown plans, no execution | `skill_view(name='plan')` |
| `change-test-loop` | 2.0.0 | LEARN-RED-GREEN-REFACTOR loop — lesson-aware memory, confidence scoring, retry limits, TDD discipline. Every cycle begins by searching past lessons. | `skill_view(name='change-test-loop')` |
| `lesson-aware-agent` | 1.0.0 | Universal lesson injection — search lessons before every action, save lessons after every fix. Works across all skills. | `skill_view(name='lesson-aware-agent')` |
| `public-contribution` | 1.0.0 | After any improvement, evaluate whether it's public-worthy for the Hermes Cortex OSS community, genericize, and contribute | `skill_view(name='public-contribution')` |
| `session-manager` | 1.1.0 | Session checkpoint/restore, context compression, progress tracking. Uses `.hermes-cortex/sessions/current.md` for active state | `skill_view(name='session-manager')` |
| `state-orchestrator` | 1.0.0 | Info routing — live context vs session vs memory vs docs | `skill_view(name='state-orchestrator')` |
| `save-lesson` | 1.1.0 | Auto-save bug-fix lessons, promote to skills, handle structured bug reports (P0/P1/P2 triage) | `skill_view(name='save-lesson')` |
| `subagent-driven-development` | 1.0.0 | Execute plans via delegate_task subagents (2-stage review) | `skill_view(name='subagent-driven-development')` |
| `systematic-debugging` | 1.0.0 | 4-phase root cause debugging | `skill_view(name='systematic-debugging')` |
| `requesting-code-review` | 1.0.0 | Pre-commit review: security scan, quality gates, auto-fix | `skill_view(name='requesting-code-review')` |
| `spike` | 1.0.0 | Throwaway experiments to validate ideas before build | `skill_view(name='spike')` |
| `memory-architecture` | 1.0.0 | Agent memory system — MEMORY.md structure, privacy, gitignore | `skill_view(name='memory-architecture')` |
| `ecosystem-audit` | 1.0.0 | Evaluate third-party tools for adoption, integration, or removal | `skill_view(name='ecosystem-audit')` |

## DevOps (5 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `moses-inbox-remediation` | 1.0.0 | Auto-remediate hermes-cortex issues reported by peer agents via agent inbox — reads remediation markers, applies fixes, marks done | `skill_view(name='moses-inbox-remediation')` |
| `nginx-security-pipeline` | 1.0.0 | Self-maintaining nginx security pipeline — IP blocking, fail2ban, atomic deploy, and daily scanner for nginx reverse proxies. Platform-aware (macOS/Linux). | `skill_view(name='nginx-security-pipeline')` |
| `nginx-web-app-deployment` | 1.0.0 | Deploy web apps behind nginx — upstream config, SSL, rate limiting, launchd/systemd, multi-layer testing | `skill_view(name='nginx-web-app-deployment')` |
| `package-security` | 1.0.0 | Age-gated package installation — verifies packages are ≥14 days old before install. Covers PyPI, npm, crates.io, Homebrew. | `skill_view(name='package-security')` |
| `weekly-auto-fix` | 1.1.0 | Auto-fix + verify known issues found by the weekly opportunity scan — git pull, branch cleanup, Docker restart, permission fixes, disk cleanup, then verify each fix | `skill_view(name='weekly-auto-fix')` |

### Infrastructure Scripts (deployed via cortex-update.sh)

| Script | Type | Purpose | Schedule |
|--------|------|---------|----------|
| `collect-agent-skills.sh` | no_agent | Agent-side: diffs local skills against upstream repo, reports custom skills to Moses inbox | every 6h per agent |
| `request-skill-reports.sh` | no_agent | Moses-side: sends inbox broadcast to all registered agents requesting skill reports | daily 2:05am |
| `process-skill-reports.py` | no_agent | Moses-side: reads skill-report messages from inbox, compiles digest for review | every 6h (:15) |

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
  `change-test-loop` (v2.0.0) and `plan` (v2.1.0) respectively — they are no
  longer standalone skills.
- **`skill-from-lesson`** has been absorbed into `save-lesson` (v1.1.0).
- **`documentation-maintenance-audit`** has been absorbed into `project-readiness`
  (local-only, not yet contributed to the public repo).
- All skills within a category share consistent tooling conventions.

## Version History

| Date | Change |
|------|--------|
| 2026-06-11 | Initial manifest — 9 skills ported from AgentKore |
| 2026-06-11 | TDD merged into change-test-loop (v1.1.0), writing-plans merged into plan (v2.1.0) |
| 2026-06-09 | Added public-contribution, skill-from-lesson (software-development), nginx-web-app-deployment (devops), SOUL.md template, updated nginx template |
| 2026-06-09 | Added pr-review (github), package-security (devops). skill-from-lesson absorbed into save-lesson (v1.1.0). documentation-maintenance-audit absorbed into project-readiness. |
|| 2026-06-15 | Added moses-inbox-remediation devops skill v1.0.0 — auto-remediate hermes-cortex issues from agent inbox messages |
|| 2026-06-15 | weekly-auto-fix v1.1.0 — added verification phase: each fix re-checks its condition post-fix with PASS/FAIL/WARN output |
|| 2026-06-17 | Added skill collection pipeline: collect-agent-skills.sh (agent-side reporter), request-skill-reports.sh (Moses orchestrator), process-skill-reports.py (digest compiler). Inbox server filename collision fix (microsecond precision). |
|| 2026-06-12 | **Memory That Compounds** — change-test-loop v2.0.0 adds LEARN phase (search lessons before every code change). New lesson-aware-agent skill for universal injection. Daily lesson auto-miner (02:00 KST). Compound stats dashboard (02:30 KST). Replaced weekly mining with daily mining. |