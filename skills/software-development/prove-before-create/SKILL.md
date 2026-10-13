---
name: prove-before-create
version: 1.0.0
category: software-development
description: >-
  Enforce the "prove existing can't handle it" discipline before creating
  any new file. Supplements survey-before-action with the HARD RULE that
  every agent defaults to "extend existing" first. Prevents codebase
  fragmentation from unnecessary parallel systems.
pinned: true
related_skills:
  - survey-before-action
  - cortex-preflight
  - session-orchestration
---

# Prove Before Create — Don't Rebuild What Exists

**The single most expensive mistake is creating a new file when an existing
one could be extended.** Every new file is debt that compounds: review time,
merge conflicts, doc drift, and confusion for future agents about which of
two parallel systems is canonical.

This skill enforces the "update existing before creating new" rule.

## When to Load

Load this skill whenever you are about to create a new:
- Script (`ops/scripts/` or `~/.hermes-cortex/scripts/`)
- Config (cron, installer, env)
- Cron job definition
- Skill (`skills/<category>/<name>/`)
- Bus message type or schema
- Agent profile or SOUL.md
- Documentation file

## The 4-Step Survey

### Step 1: Search with 3+ different terms

```bash
search_files(pattern="<term-1>", path="~/hermes-cortex/ops/scripts/", target="files")
search_files(pattern="<term-2>", ...)   # different angle
search_files(pattern="<term-3>", ...)   # synonym / broader concept
skills_list()
cronjob(action="list")
```

**One search is not a survey.** If nothing matches term-1, you haven't
proven the gap exists. Try term-2 and term-3 before concluding.

### Step 2: Load matching skill references

When a skill name matches, call `skill_view(name)` and check its linked
files. A skill's `references/` directory may contain:

- A ready-to-use script you were about to build
- A template you can copy and modify
- An example that shows the exact wiring pattern

These ARE the solution. Don't rebuild them.

### Step 3: Extend — don't rebuild

If the capability exists but isn't wired, **wire it**:

| Capability state | What to do |
|-----------------|------------|
| Skill has technique but no CLI script | Add a CLI entry point to the skill |
| Script has logic but no cron | Wire it as a cron with `cronjob action='create'` |
| CLI exists but no `--json` flag | Add `--json` to the existing script |
| Config template exists but no install path | Add a `register()` call to `cortex-update.sh` |
| Capability exists in one codebase but not another | Port it, don't rewrite it |
| Capability exists only as a SKILL, bound to a system you are moving off | Port the capability to a system-neutral tool; say explicitly what the existing skill covers and what the gap actually is |
| Capability is blocked by a runtime dependency the target hosts lack | Replace the dependency (e.g. compile the database engine in) rather than requiring a host install |

Adding a flag to an existing system costs 1/10th the debt of a new
parallel system.

### Step 4: If you still create something new

Document in the commit message:
1. What terms you searched
2. What you found (and why it didn't fit)
3. The minimum viable scope of the new file

Name the file at the **class level**, not after today's session artifact.
A file called `fix-registry-timeout.py` is wrong (session-specific).
A file called `circuit-breaker.py` is right (class-level).

## Choose the Implementation Stack by MEASURING the Host

Creating a new tool is also a choice of language, runtime, and dependencies — and that choice is a
"create" decision with the same debt. **Measure before you pick; never adopt a suggested stack on
its reputation.**

```bash
<compiler> --version            # is the suggested language even installed?
ls ~/.cargo/registry/cache/*/   # can the dependency set resolve OFFLINE?
command -v <helper>             # does the external binary your design leans on exist?
```

- **Prefer a language the fleet already ships.** A language nobody builds in today adds a toolchain,
  a CI path, and a security surface to every host — even when it wins a benchmark.
- **Prefer zero RUNTIME dependencies over zero BUILD dependencies.** A tool that needs an external
  binary or interpreter at run time fails on the host that lacks it, silently; a library compiled
  into the binary costs one build and then works everywhere. Watch for a fallback that degrades
  quietly (a cache that reports itself unavailable is indistinguishable from an empty one).
- **Match the consumer's language when a system will link the code**, and expose a CLI/stdio surface
  so other systems can consume it without importing it.
- Record the measured facts in the design doc, and re-measure the envelope (binary size, idle RSS)
  instead of repeating an estimate — a design justified by someone else's number is an assumption.

## Violation Classification

Creating a new file when an existing system could be extended is a
**structural violation**. It:

- Fragments the codebase into parallel systems
- Increases review time for every future change
- Creates merge conflicts between the two systems
- Confuses future agents about which is canonical
- Compounds with every new file

If you catch yourself mid-creation with a "this is faster to write than
find the existing one" thought — stop. That thought is wrong. Surveying
saves more time than writing.

## Pitfalls

| Pitfall | Why it's wrong |
|---------|----------------|
| "I'll search later" | You won't. Search BEFORE writing. |
| "This is different enough" | 80% overlap means extend the existing tool. |
| "The existing one is poorly written" | Improve it. Don't abandon it — that's how you get 3 half-written libraries. |
| "It's faster to just write it" | Faster NOW, slower forever. Every new file is a permanent tax. |
| Searched once, nothing found | One search is not a survey. Try 3 different search terms. |
| Found a match but didn't load its references | The references/ dir may contain the exact solution. |

## Relationship to Other Skills

- **survey-before-action** (Hermes Cortex) — covers the general survey
  checklist. This skill adds the enforcement layer and the "extend, don't
  rebuild" rule.
- **cortex-preflight** (repo-specific) — adds git search and deployment
  checks. Run after this skill.
- **session-orchestration** — Wave 1 (Discovery) should include the 4-step
  survey before proceeding to implementation.
