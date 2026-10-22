# External Skill Evaluation — Worked Example: dhh-rails-style

Durable profile from the 2026-08-26 evaluation. A future session asked to
evaluate this skill again (or a sibling variant) should start from here,
not re-research from zero. Also serves as a worked example of the Phase 0
Value & Fit Assessment in SKILL.md.

## The Skill

- **Name:** `dhh-rails-style` — encodes DHH/37signals Rails conventions for
  WRITING new Ruby/Rails code (REST purity, fat models / thin controllers,
  state-as-records, Current attributes, Hotwire/Turbo/Stimulus, Minitest +
  fixtures, minimal gem diet).
- **Canonical source:** `ratacat/claude-skills` on GitHub
  (`skills/dhh-rails-style/`). Derived from Marc Köhlbrugge's "Unofficial
  37signals/DHH Rails Style Guide", 265 PRs from 37signals' Fizzy/Campfire
  codebase, the Rails Doctrine, and DHH's Rails World 2025 keynote.
- **Structure:** routing-style SKILL.md (~7KB) with an intake table → 6
  reference files (~50KB total): controllers.md, models.md, frontend.md,
  architecture.md, testing.md, gems.md. Token-efficient: reads only the
  reference for the current task.
- **Variants (same content family, different owners):** `dhh-coder`
  (majesticlabs-dev, SkillsMP), `rails-dhh` (diegosouzapw, agentskill.sh),
  compound-engineering-plugin (kieranklaassen, DeepWiki). The ratacat copy
  is the most complete — use it as canonical.
- **Companion:** `dhh-rails-reviewer` (same repo) — brutally-honest Rails
  code review from DHH's perspective. Useful review lens for the legacy app.

## Licensing Caveat

Code examples in the skill were extracted from 37signals' Fizzy codebase,
licensed under the O'Saasy License. Treat them as PATTERN GUIDANCE, not
verbatim copy — copy-pasting into client codebases carries license risk.
Disclaimers in the skill itself: LLM-generated, may contain inaccuracies,
not affiliated with or endorsed by 37signals.

## Fleet Verdict (2026-08-26)

- **Fleet's actual Rails exposure:** legacy music copyright/royalty app
  (Korean/English i18n, CPLEX/CSV imports) — documented in our own
  `rails-data-pipeline-debugging` and `batch-job-optimization` skills.
  That work is LEGACY MAINTENANCE/DEBUGGING.
- **Verdict: niche value.** dhh-rails-style is a NEW-CODE style guide; it
  would NOT have helped any documented legacy incident (split_title
  heuristics, import loops). Value surfaces only for (1) reviewing Rails
  changes with a consistent lens, (2) greenfield Rails work, (3) its
  philosophy alignment (database-over-Redis, minimal deps, DB constraints
  over validations) which matches the fleet's Postgres-everything posture.
- **The lesson that generalizes:** a style guide for WRITING code has
  near-zero value for legacy DEBUGGING work — even when the same
  technology appears in both. Ground adoption verdicts in the fleet's
  actual WORK TYPE, not the tech name.
- **Standing recommendation:** install cost is trivial (~50KB markdown, no
  scripts, triggers only on Rails work). Lean install (with
  dhh-rails-reviewer) IF the legacy Rails app remains active; skip if Rails
  work winds down. Third-party repo → run the skill-vetting safety pass
  before install regardless.

## Re-finding Sources (if re-research is needed)

Marketplaces that mirror/host it: skillsmp.com, lobehub.com/skills,
agentskill.sh, eliteai.tools, playbooks.com, agent-skills.md. Search term
that works: `dhh rails skill` — the canonical GitHub file is
`ratacat/claude-skills/blob/main/skills/dhh-rails-style/SKILL.md`.
