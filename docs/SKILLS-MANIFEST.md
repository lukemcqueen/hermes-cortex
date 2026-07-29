# Skills Manifest — Hermes Cortex

Skills in this repo auto-install via `install.sh` step 10, which
recursively copies `skills/` to `~/.hermes/skills/`, preserving category
subdirectories. Skills are distributed across multiple categories matching
their domain.

## GitHub (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `pr-review` | 1.0.0 | Full PR review pipeline — whole-repo context, architecture analysis, lesson-DB pattern matching, test regression check, and formal review with inline comments. Zero external API costs. | `skill_view(name='pr-review')` |

## Software Development (21 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `requirements-elicitation` | 1.1.0 | Requirements elicitation — deep/fast modes, RICE/MoSCoW, domain question banks | `skill_view(name='requirements-elicitation')` |
| `architecture-review` | 1.1.0 | Multi-role architecture review — 6 roles, weighted decision matrix. Integrated with codebase-design for deep module vocabulary. | `skill_view(name='architecture-review')` |
| `story-decomposition` | 1.0.0 | Break features into user-visible, testable stories with INVEST | `skill_view(name='story-decomposition')` |
| `product-requirements` | 1.0.0 | Concise 1-page PRD template — 14 sections | `skill_view(name='product-requirements')` |
| `agent-flow` | 1.1.0 | Workflow router — 12 patterns, manifest-aware skill loading (always + on_task from .hermes-cortex/skills.yaml) | `skill_view(name='agent-flow')` |
| `agent-contract` | 1.0.0 | Non-negotiable execution rules — real work, no simulation | `skill_view(name='agent-contract')` |
| `agent-inbox` (skill) | `agent-inbox` | 1.0.0 | Web-based agent messaging system (previously Agent Inbox) — topic channels, thread support, priority field, JSON API | `skill_view(name='agent-inbox')` |
| `dev-plan` | 2.1.0 | Plan mode — write actionable markdown plans, no execution | `skill_view(name='dev-plan')` |
| `change-test-loop` | 2.0.0 | LEARN-RED-GREEN-REFACTOR loop — lesson-aware memory, confidence scoring, retry limits | `skill_view(name='change-test-loop')` |
| `lesson-aware-agent` | 1.0.0 | Universal lesson injection — search lessons before every action, save lessons after every fix | `skill_view(name='lesson-aware-agent')` |
| `public-contribution` | 1.0.0 | After any improvement, evaluate whether it's public-worthy and contribute | `skill_view(name='public-contribution')` |
| `session-manager` | 1.1.0 | Session checkpoint/restore, context compression, progress tracking | `skill_view(name='session-manager')` |
| `state-orchestrator` | 1.0.0 | Info routing — live context vs session vs memory vs docs | `skill_view(name='state-orchestrator')` |
| `subagent-driven-development` | 1.0.0 | Execute plans via delegate_task subagents (2-stage review) | `skill_view(name='subagent-driven-development')` |
| `save-lesson` | 1.1.0 | Auto-save bug-fix lessons, promote to skills, handle structured bug reports | `skill_view(name='save-lesson')` |
| `root-cause-debugging` | 2.0.0 | **6-phase** root cause debugging: feedback loop, reproduce, pattern, hypothesise, fix, cleanup. Ported from Matt Pocock's diagnosing-bugs. | `skill_view(name='root-cause-debugging')` |
| `code-review` | 3.0.0 | **Two-axis** pre-commit review: Standards (conventions + Fowler smells) + Spec (requirements). Parallel sub-agents. Plus security scan + auto-fix. Ported from Matt Pocock's code-review. | `skill_view(name='code-review')` |
| `codebase-design` | 1.0.0 | **NEW** — Deep module vocabulary: module, interface, depth, seam, adapter, leverage, locality. Design testable modules with clean seams. Ported from Matt Pocock. | `skill_view(name='codebase-design')` |
| `memory-architecture` | 1.0.0 | Agent memory system — MEMORY.md structure, privacy, gitignore | `skill_view(name='memory-architecture')` |
| `ecosystem-audit` | 1.0.0 | Evaluate third-party tools for adoption, integration, or removal | `skill_view(name='ecosystem-audit')` |

## DevOps (5 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `inbox-remediation` | 1.0.0 | Auto-remediate hermes-cortex issues reported by peer agents via the Agent Bus (previously Agent Inbox) — reads remediation markers, applies fixes, marks done | `skill_view(name='inbox-remediation')` |
| `nginx-security-pipeline` | 1.0.0 | Self-maintaining nginx security pipeline — IP blocking, fail2ban, atomic deploy, and daily scanner for nginx reverse proxies. Platform-aware (macOS/Linux). | `skill_view(name='nginx-security-pipeline')` |
| `nginx-web-app-deployment` | 1.0.0 | Deploy web apps behind nginx — upstream config, SSL, rate limiting, launchd/systemd, multi-layer testing | `skill_view(name='nginx-web-app-deployment')` |
| `package-security` | 1.0.0 | Age-gated package installation — verifies packages are ≥14 days old before install. Covers PyPI, npm, crates.io, Homebrew. | `skill_view(name='package-security')` |
| `orch-weekly-auto-fix` | 1.1.0 | Auto-fix + verify known issues found by the weekly opportunity scan — git pull, branch cleanup, Docker restart, permission fixes, disk cleanup, then verify each fix | `skill_view(name='orch-weekly-auto-fix')` |

### Infrastructure Scripts (deployed via cortex-update.sh)

| Script | Type | Purpose | Schedule |
|--------|------|---------|----------|
| `agent-learning-collector.py` | no_agent | Agent-side: collects skills delta, lessons delta, session stats; sends Learning Report to Moses via Agent Bus | every 6h per agent |

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
- `ak-elicit` → `requirements-elicitation`
- `ak-party` → `architecture-review`

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
| 2026-06-15 | Added inbox-remediation devops skill v1.0.0 — auto-remediate hermes-cortex issues from agent inbox messages |
| 2026-06-15 | orch-weekly-auto-fix v1.1.0 — added verification phase: each fix re-checks its condition post-fix with PASS/FAIL/WARN output |
| 2026-06-17 | Added skill collection pipeline: collect-agent-skills.sh (agent-side reporter), request-skill-reports.sh (Moses orchestrator), process-skill-reports.py (digest compiler). Inbox server filename collision fix (microsecond precision). |
|| 2026-06-12 | **Memory That Compounds** — change-test-loop v2.0.0 adds LEARN phase (search lessons before every code change). New lesson-aware-agent skill for universal injection. Daily lesson auto-miner (02:00 KST). Compound stats dashboard (02:30 KST). Replaced weekly mining with daily mining. |
|| 2026-07-07 | **Pocock Upgrade** — Three skills imported/upgraded from Matt Pocock's skills repo (159k ★). New `codebase-design` (deep module vocabulary). `root-cause-debugging` v2.0 (6-phase with feedback loop). `code-review` v3.0 (two-axis Standards + Spec with Fowler smells). Integrated into agent-flow and architecture-review. |