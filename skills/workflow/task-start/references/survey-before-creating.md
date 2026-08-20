# Survey Before Creating — Cron, Script & Mechanism Audit

## Why This Exists

Three corrections in one session: agent created `local-*` crons without surveying existing ones, when existing `agent-*` crons could have been extended. Root cause: the survey step was skipped even though `survey-before-action` was supposedly "loaded."

The ritual is: load skills → **actually run the survey tools** → create only if nothing fits.

## Mandatory Pre-Creation Survey

**Before creating ANY new cron, script, file, mechanism, or document, run these in order. Skipping this sequence is a trust violation — I was corrected on this three separate times in one session (created crons without surveying, created docs without loading the scope skill).**

### Step 1 — Survey domain skills

After classifying the task with agent-flow, call `skills_list()` for the identified domain category. If your domain is not a category, search with 3+ related terms. **Every matching skill must be loaded with `skill_view()` before you write any code or create any file.** A skill not loaded is a mistake waiting to happen.

**Examples:**
- Creating a new cron → domain is "devops" → `skills_list(category='devops')` → check `cron-job-management`, `cron-format-standard`, etc. before writing anything
- Creating architecture docs → domain is "documentation" → `skills_list()` doesn't have a documentation category → search "documentation" with 3 terms → load `documentation-scope` first. The scope banner convention exists specifically to prevent writing docs that can't be used by the public repo.
- Creating a new script → `skills_list(category='devops')` → check if any existing skill covers the same functionality by reading descriptions and SKILL.md references

### Step 2 — Survey existing crons

Run `cronjob(action='list')` and read the full output. Note every cron that covers related territory. **If one exists, extend it** — do not create a parallel system. The `scoring-activity-watchdog` already existed when I created `local-cron-cost-report` and `local-trace-quality-watchdog` — extending the watchdog was the right call, creating new crons was wrong.

### Step 3 — Search repo for existing scripts

Run `search_files()` with **3+ different terms** for the script name and purpose. Check `ops/scripts/` for existing scripts that do this or could be extended. Also check `~/.hermes-cortex/scripts/` for deployed copies that might differ from repo source.

### Step 4 — Check if existing can absorb the new capability

Before creating ANY new file:
1. Does an existing cron already run at a compatible cadence? → Extend it
2. Does an existing script already handle related data? → Add to it
3. Does an existing skill already cover the territory? → Add a pitfall/reference
4. Only if ALL answers are NO → create new. Document the survey result.

### Step 5 — For research/documentation tasks: survey companion repos

When the task involves reviewing external repos and writing synthesis docs or PRDs:

1. Extract target repo READMEs
2. **Scan each README for companion/ecosystem repos** — "See also", "Companion", stack diagrams, footer links
3. Extract EVERY companion repo too — they contain the critical missing layers
4. Map the relationship: `memory → loops → runtime → governance → fleet`
5. Search for real-world production research (post-mortems, failure patterns, benchmarks)
6. Only then synthesize across all sources

> **Failure (2026-07-23):** Reviewed 4 target repos for PRD creation, missed 5 companion repos explicitly linked in their READMEs. PRD v1 was incomplete — had to rewrite as v2 after user correction. See `self-improvement-pipeline/references/research-synthesis.md`.

### Step 6 — Make the call

- **Existing system found that can be extended?** → Extend it. Add the new capability to the existing cron/script.
- **Nothing matched after 3+ searches?** → Only then create new. Document the survey result in your feedback note.

## Cron Naming Rules

| Prefix | Scope | Install method |
|--------|-------|---------------|
| `agent-*` | All agents benefit | Register in `install-crons.sh` |
| `orch-*` | Orchestrator-only (Moses, Esther) | Register in `install-orch-crons.sh` |
| `local-*` | This server only | Create via `cronjob action='create'` |

If the capability benefits ALL agents (cost tracking, quality monitoring, scoring, Langfuse analytics), it MUST use `agent-*` prefix. A `local-*` cron for fleet-relevant work will be corrected.

## Document the Result

After surveying, include in your feedback_accept note:

```
Surveyed: found <cron-name>, chose to extend | nothing matched
```

This makes the survey visible and auditable in the governance record.
