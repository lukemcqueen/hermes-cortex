# Harness-Doc Conflict Check — PLAN (2026-11-06)

## Problem (measured)

The `hermes-cortex → steadfaste-fleet` rename (940-file sweep, 2026-11-04) swept
repo-tracked files but MISSED host-level harness-integration files, and nothing
detected the miss. Incidents, each recorded in a governance cycle
(`loop-governance.db`) — cited instead of re-explained:

- `~/.claude/CLAUDE.md` carried retired `~/hermes-cortex` / `~/.hermes-cortex`
  paths (fixed in cycle #14213 `fix-claude-agent-paths`).
- `~/.steadfaste-fleet/SOUL.md` carried a stale `~/.hermes-cortex/state/...` lock
  path (removed in cycle #14212 `remove-fleet-soul-leftover`).
- `hermes-cortex-setup` skill body + deployed `gateway-pi.example.yaml` carried
  retired paths (fixed in cycle #14207, commit `1dce14da`).

Root cause: the doctor enumerates REPO surfaces and a few harness surfaces, but
there is NO check that the cross-client harness files (Claude, Pi, Codex, custom)
still agree with the CANONICAL facts AGENTS.md establishes — product name,
canonical paths, the absence of the retired name/paths.

## What already exists (do not duplicate)

- `check_dev_repo_claude` (`fleet_doctor/checks.py:786`) — dev repos have a
  CLAUDE.md with the `## Excellence — Core Value, Every Action` heading.
- `check_dev_repo_agents` (`checks.py:669`) — dev repos have AGENTS.md.
- Pi harness check (`checks.py:3288`).
- `agents-doc-audit.py` — mandatory-section presence for AGENTS.md + SOUL.md.
- `doc-freshness` skill §"Adding a New Mandatory Section": "for each
  non-auto-syncing surface add a doctor check that WARNs (never auto-overwrites)".

The missing piece: a check for the **host-level** harness files AND a
**canonical-token conflict** check against them (the doc-freshness skill checks
HEADING presence, never stale-path/name tokens).

## Design

### 1. New doctor check `check_harness_doc_conflicts`

Modeled on the existing `check_repo_map` / `skill-drift-parity` pattern: enumerate
the harness files, grep them for conflicting canonical tokens, FAIL/WARN with a
`fix:` line. Never auto-rewrite (files are host/project-owned).

**Enumerated harness-integration surfaces (the "things we integrate"):**

| Surface | Path | Ownership |
|---|---|---|
| Claude user instructions | `~/.claude/CLAUDE.md` | host |
| Claude settings | `~/.claude/settings.json` | host |
| Pi MCP manifest | `~/.pi/agent/mcp.json` | host |
| Pi settings | `~/.pi/agent/settings.json` | host |
| Pi harness extensions | `~/.pi/agent/settings.json` `extensions` (same file) | host |
| Cross-client skills pointer | `~/.agents/skills` (symlink) | host |
| Repo Claude contract | `<repo>/CLAUDE.md` | repo |
| Repo MCP manifest | `<repo>/.mcp.json` | repo |

### 2. What "conflict with AGENTS.md" means (the check predicate)

AGENTS.md is the canonical source of the fleet's internal facts. The check
derives the RETIRED tokens that AGENTS.md no longer contains and greps each
harness file for them:

- DOTTED paths (the runbook's discrimination rule — these must reach ZERO):
  `~/.hermes-cortex`, `.hermes-cortex/` (absolute + tilde forms), `~/hermes-cortex`.
- Retired product name: `Hermes Cortex` (title-case, outside the 3 deliberately
  kept skill `name:` identifiers).

**Deliberate keeps (excluded; same list as `docs/rename-followups-steadfaste-fleet.md`):**
- the 4 skill dirs + `name:` frontmatter (`hermes-cortex`, `hermes-cortex-setup`,
  `hermes-cortex-repo-deploy`, `hermes-cortex-maintenance`);
- enforcer dual-URL accept list (`hermes-cortex|steadfaste-fleet`) — detection subject;
- migration tools (`migrate-home-dirs.sh`, `fleet-set-origin.sh`, `verify-rename-*.sh`);
- `docs/older/` + `docs/evidence/` historical records.

The check reports: `FAIL` when a REPO-owned file carries a retired dotted path;
`WARN` when a HOST-owned file (not repo-tracked) does — both with a `fix:` line
naming the repoint and `docs/runbooks/fleet-local-dir-rename.md`.

### 3. Single source of truth for the retired-token list

Keep the retired-token + keep-list in ONE place the doctor reads (a small
`docs/harness-canonical-facts.yaml`, or a constant in checks.py beside
`check_repo_map`). Reusing the existing `docs/rename-followups-steadfaste-fleet.md`
keeps list avoids inventing a third enumeration.

## Sizing / slicing

**Pro review 2026-11-06:** `adversarial-review.py --cycle-id 14214 --re-review`,
reviewer `deepseek/deepseek-v4-pro-0813`. Verdict **CLEAN**, 0 findings (one
`unverified-claim` on the incident list was resolved by citing the cycle ids /
commit above). Per the plan-review rule, CLEAN validates the plan's claims, not
its predicted consequences — the build cycle's RED plant test falsifies those.

1. **This cycle — plan + pro review** (no build): commit this doc + the recorded review row.
2. **Build cycle** — add `check_harness_doc_conflicts` to `checks.py` + register the
   check + the token/keep list; wire it into the doctor; verify: doctor detects a
   PLANTED stale token (RED) and a clean host (GREEN), pre-existing harness files
   now clean or flagged; deploy + push.

## Risks

- **False positives** on the title-case product name (a historical project name)
  → scope the name-token to the harness files only, keep the path-token as the
  load-bearing check.
- **The check can only see THIS host's files** — fleet coverage is per-host
  doctor, which matches how the doctor already works.