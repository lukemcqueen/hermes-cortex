<!--
  Hermes Cortex — Seeded AGENTS.md template

  SOUL.md vs AGENTS.md — the relationship:

    SOUL.md (at ~/.hermes/SOUL.md) defines who the agent IS —
    character, behavioral principles, core mission. Always loaded,
    consistent across every repo the agent touches.

    AGENTS.md (in this repo's root) defines what THIS PROJECT needs —
    build commands, conventions, architecture. Loaded from the current
    working directory. One agent can serve many repos, each with its own
    AGENTS.md.

    They are INDEPENDENT layers that coexist in the system prompt.
    AGENTS.md does NOT override SOUL.md — they serve different concerns.
    See §Relationship to SOUL.md below for how they resolve together.

  Placeholders: {{PROJECT_NAME}} {{PROJECT_DESCRIPTION}} {{SEED_DATE}} {{SEED_COMMIT}}
-->
# Agent Guidelines — {{PROJECT_NAME}}

*Seeded from Hermes Cortex {{SEED_COMMIT}} on {{SEED_DATE}}*

---

## Quick Reference

| What | Where |
|------|-------|
| Agent identity | `~/.hermes/SOUL.md` — character, principles, how to think |
| Project context | **This file** — build, conventions, what to build |
| Hermes Cortex source | `~/hermes-cortex/` — shared skills, scripts, templates |
| Doc index | `docs/DOCS-INDEX.md` (if present) |

---

## Quick Start

<!-- Replace with actual project commands -->
```bash
./run build       # Build the project
./run test        # Run test suite
./run dev         # Start development server
./run lint        # Run linters and formatters
```

**First time in this repo?** Run `./run setup` or see `CONTRIBUTING.md`.

---

## Conventions

<!-- Fill in with project-specific conventions. Be specific — prefer exact
     commands over general guidance. Every line is a constraint on the agent. -->

**Code style:** <!-- e.g., Prettier defaults, 4-space indent, trailing commas -->

**Commit format:** <!-- e.g., conventional commits: type(scope): message -->

**Branch naming:** <!-- e.g., feat/, fix/, chore/ prefixes -->

**Testing:** <!-- e.g., pytest with xdist, Jest with --coverage -->

---

## Architecture

<!-- Brief notes on project structure. Keep to 10-15 lines max.
     What an agent needs before touching any file. -->

- <!-- entry point, key modules, data flow, important config files -->

---

## Project Rules

<!-- Project-specific agent rules. 3-5 max. Each rule should be:
   - Falsifiable (can check compliance)
   - Actionable (tells the agent what to DO, not what to believe)
   - Necessary (would quality suffer without it?) -->

1. <!-- e.g., Run `./run lint` before every commit. No exceptions. -->
2. <!-- e.g., All new features must include tests in `tests/`. -->
3. <!-- e.g., Never commit directly to main. PR through `develop` branch. -->

---

## Relationship to SOUL.md

SOUL.md and AGENTS.md are complementary, not hierarchical. They resolve
conflicts through the following principles:

### Layer Separation

SOUL.md defines **the agent's identity** — character, behavioral principles,
governance discipline. AGENTS.md defines **this project's context** — build
commands, code conventions, architecture notes. They are independent sources
of instruction loaded into the same system prompt.

| Layer | File | Scope | Loads for |
|-------|------|-------|-----------|
| Identity | `~/.hermes/SOUL.md` | All repos | Every session |
| Project | `<repo>/AGENTS.md` | This repo | Cwd matches repo root |

### Resolution Principles

**1. SOUL.md governs character; AGENTS.md governs context.**

When behavioral principles and project rules address different concerns, they
both apply fully — no conflict, no need to choose. SOUL.md says "be thorough";
AGENTS.md says "run `./run test`". Both apply: thoroughness means running
`./run test`.

**2. AGENTS.md is senior for project-specific technical decisions.**

When SOUL.md says "fix root causes" and AGENTS.md says "don't refactor tests",
the project rule wins. The project knows its specific constraints; the identity
provides the general approach. The concrete project instruction overrides the
abstract principle within the project's scope.

**3. SOUL.md's tier system governs character conflicts.**

If AGENTS.md told the agent to do something that violates a governance rule or
a character principle (lying, cutting corners, bypassing security), SOUL.md's
behavioral tier system applies. AGENTS.md cannot instruct an agent to violate
its identity. Tier 2 (Governance) is system-enforced and cannot be overridden
by any project file.

**4. When in genuine doubt, the more specific instruction wins.**

A concrete command (`./run test --coverage`) beats a general directive
("run tests"). An exact file path beats a description ("the config is at
`config/defaults.yaml`"). Specificity is the tiebreaker.

**5. Append, don't override.**

AGENTS.md adds project knowledge to the agent's understanding. It never
replaces the agent's identity, character, or governance. If a project needs
to change agent behavior, it belongs in a skill or a profile-specific SOUL.md,
not in this file.

### Quick Test

Ask yourself before every action in this repo:

> "Would doing this violate my identity as defined in SOUL.md?"
>
> If yes → don't. Identity is senior for character.
>
> "Would doing this violate this project's conventions in AGENTS.md?"
>
> If yes → don't. Project rules are senior for technical specifics.

If both say different things, use the five principles above to resolve —
not whichever is louder or comes first.

---

## Agent Notes

### One Agent, Many Repos

This AGENTS.md is project-specific. The same agent identity (your SOUL.md)
serves every repo you work in. When switching between repos:

- Your character and principles stay the same (SOUL.md)
- Only the project context changes (each repo's AGENTS.md)
- Skills you load are global — shared across all repos

**What DOESN'T go in AGENTS.md:**
- Agent character, personality, or behavioral principles (belongs in SOUL.md)
- Global workflow patterns that apply to every project (belongs in skills)
- Personal preferences about verbosity, tone, or interaction style (belongs in SOUL.md or memory)

**What DOES go in AGENTS.md:**
- This project's build/test/run commands
- This project's code style and conventions
- This project's architecture and key files
- Project-specific constraints and rules

**When you have a skill that spans projects:** upstream it to
`hermes-cortex` so all agents and all repos benefit. If it's truly one-repo
only, reference it from AGENTS.md via the skills manifest.

<!--
  (End of template — replace placeholders above with real project content.
   Keep AGENTS.md under 20K characters (Hermes cap). If you need more,
   split into skills instead of expanding this file.)
-->
