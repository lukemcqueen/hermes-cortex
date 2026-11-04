# Rename follow-ups: hermes-cortex → steadfaste-fleet (for agents)

The product/repo was renamed `hermes-cortex` → `steadfaste-fleet` (and the brand
`Hermes Cortex` → `Steadfaste Fleet`). A repo-wide sweep renamed 4,648
occurrences across 938 tracked files (docs, scripts, crons, Pi harness, README,
skills bodies, AGENTS/CLAUDE/CONTRIBUTING). This file records what was
DELIBERATELY left as `hermes-cortex`/`Hermes Cortex` and why, so a later reader
does not "fix" it.

## Deliberately NOT renamed (do not touch)

1. **Skill directory names + `name:` frontmatter** for these four skills — the
   name is the `skill_view(name=...)` load key; renaming it breaks every load:
   - `skills/autonomous-ai-agents/hermes-cortex/`
   - `skills/autonomous-ai-agents/hermes-cortex-setup/`
   - `skills/devops/hermes-cortex-maintenance/`
   - `skills/devops/hermes-cortex-repo-deploy/`
   Rename these only with a fleet-wide skills-manifest + registration sweep, not
   here.

2. **Enforcement / detection** (`plugins/governance-enforcer/`,
   `mcp-servers/`, `tests/test_enforcer_pii_gate.py`) — the enforcer
   reports the OLD path as the SUBJECT of its messages and pins the dual-URL
   accept list `(hermes-cortex|steadfaste-fleet)`; renaming falsifies detections.
   (.mcp.json is NOT in this list — it is the live pi-client MCP manifest and was
   repointed from `~/.hermes-cortex/...` to `~/.steadfaste-fleet/...` when the
   transition symlinks were removed.)

3. **Migration tools** (`ops/scripts/manage/migrate-home-dirs.sh`,
   `fleet-set-origin.sh`, `verify-rename-<host>.sh`) — they must keep the OLD name
   literal for idempotency/guard matching (the tool that performs the migration).

4. **Historical/evidence records** (`docs/older/`, `docs/evidence/`) — dated
   transcripts and reports quote the old name as the thing that WAS at that
   revision; rewriting falsifies records and their checksums.

## The `cortex` short-name family is a SEPARATE naming layer (not covered)

The short name `cortex` survives throughout and was NOT renamed to `fleet`, per
the current instruction (only `hermes-cortex` → `steadfaste-fleet`):
- service/artifact names: `cortex-bus`, `cortex-update.sh`, `cortex_gateway`,
  `cortex-doctor`, `cortex-dashboard`, `mycortex`
- env var: `CORTEX_DEPLOY_HOME`
- skill dirs: `cortex-bus*`, `cortex-preflight`, `cortex-deployment-sync`, `mycortex`

If the fleet later wants `cortex` → `fleet` too, that is a SECOND, larger sweep
with its own runtime-contract risks (service names, env vars, DB roles).

## Sequencing requirement (deploy-home default)

The sweep flipped `CORTEX_DEPLOY_HOME`'s default (`${HOME}/.hermes-cortex` → the
new local path). A host that pulls this WITHOUT having renamed its local dirs
first would deploy into an empty new home and orphan its real framework. Order:
1. rename local dirs (migrate-home-dirs.sh, bus EXEC) — symlink keeps old working,
2. THEN pull this swept tree so future deploys land on the renamed home.

## Verify an agent is converged

`git grep -i hermes-cortex` == 0 in tracked in-scope files (exclusions above),
and `git grep -i "hermes cortex"` == 0 outside historical dirs.
