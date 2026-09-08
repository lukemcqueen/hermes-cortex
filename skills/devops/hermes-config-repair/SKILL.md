---
name: hermes-config-repair
description: "Use when hermes config check flags a config.yaml defect."
version: 1.0.0
category: devops
license: MIT
platforms: [linux, macos]
---

# Hermes config.yaml Structure Repair

**Trigger:** a user pastes findings from `hermes doctor` or `hermes config check`
that name a `~/.hermes/config.yaml` structure problem — a section typed as a
dict instead of a list, misplaced keys, or a recommendation to add a config
section. Distinct from `hermes-model-config` (model/provider regressions); this
skill is the general structure-repair mechanics.

## Triage the report by origin FIRST

A doctor/config-check finding list mixes different owners. Sort before editing:

- **config.yaml structure defects** ("custom_providers is a dict — it must be a
  YAML list", "Root-level keys … look like custom_providers entry fields",
  "enable sessions.auto_prune") → live config, fix here.
- **npm/dependency CVEs** ("Browser tools has N npm vulnerability", "web
  workspace has N npm vulnerabilities") → these live in the UPSTREAM
  hermes-agent node workspaces (`apps/*`, `web`, `ui-tui`), whose doctor note
  calls them build-tooling advisories that "clear via a lockfile bump."
  Never run `npm audit fix` inside `~/.hermes/hermes-agent` — that is
  NousResearch upstream code, not yours to change (boundary). Report them as
  upstream; the fix is a NousResearch lockfile bump + `hermes update`.
- **state.db too large** → config gets `sessions.auto_prune`, but pruning only
  runs at the next CLI/gateway/cron startup and does NOT shrink an already-1GB
  file — that needs `hermes sessions prune` / `hermes sessions optimize-storage`
  offline with the gateway stopped. Say so; do not claim the size dropped.

## Who ELSE rewrites config.yaml: cortex auto-convergence

When a Hermes Cortex host reports the model/fallback it manually set "keeps
disappearing" (the user's phrasing), the cause is usually NOT a Hermes migration —
it is cortex's own auto-converge. Two cortex installers invoked from
`cortex-update.sh` run `hermes config set` against Hermes' OWN `~/.hermes/config.yaml`:

- `install-model-default.sh` → rewrites `model.default` from `DEFAULT_MODEL` env /
  `~/hermes-cortex/.env` (default `deepseek-v4-flash`)
- `install-fallback-providers.py` → rewrites `fallback_providers` with the env-driven
  deepseek→opencode chain

These run on every `cortex-update.sh`, so any manual `config.yaml` model/fallback
edit is clobbered at the next deploy. They are not needed for cron resilience (cortex
LLM crons pin their model per-job in the manifest, resolved independently of
`config model.default`). Diagnose by checking `git log`/deploy history for when these
installers were wired in, and the deploy log for the convergence block firing.

**The fix is the per-host opt-out flag, not re-editing config:** set
`CORTEX_SKIP_MODEL_CONVERGENCE=1` in the gitignored `~/hermes-cortex/.env` (sourced
at the top of cortex-update.sh). Both convergence blocks then skip and Hermes config
stays as set. Guard it behind a host-scoped env flag so the fleet default converges
only where wanted — a repo-wide behavior change would silently alter other hosts.

## Edit via the sanctioned CLI, never hand-edit

`hermes config set` is the invariant path — a stray indent in hand-edited YAML
breaks the live gateway.

### Replacing an entire SECTION with a list/scalar needs `--force`

`hermes config set custom_providers '<json list>'` REFUSES: when the target
key is an existing section (a dict with sub-keys), the CLI treats a non-dict
value as a scalar error and exits 1, printing the sub-keys. It only accepts a
scalar/list replacement with:

    hermes config set --force custom_providers '[{"name":"...","base_url":"..."}]'

`--force` replaces the whole section. Confirm the CLI reports the value it set.

### The CLI strips trailing comments on any rewrite

`hermes config set` re-serializes config.yaml and DROPS trailing commented help
blocks (file visibly shrinks). That is cosmetic and safe, but you cannot tell
from size alone whether a functional key was lost.

**Before any edit:** back up, then after the edit diff the PARSED key-sets, not
the text:

    cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak-$(date +%Y%m%d_%H%M%S)
    cd ~/.hermes/hermes-agent && HERMES_HOME=~/.hermes venv/bin/python3 -c \
      "import yaml; a=yaml.safe_load(open('<bak>')); b=yaml.safe_load(open('/home/moses/.hermes/config.yaml')); print('removed', sorted(set(a)-set(b)) or 'none'); print('added', sorted(set(b)-set(a)) or 'none')"

`removed: none` + only the intended section added = the rewrite lost nothing.

### Adding a new section by dotted path creates it

`hermes config set sessions.auto_prune true` creates the `sessions:` section
if absent — no `--force` needed for a fresh leaf key.

## Verify with the REAL structure validator

`hermes config check` is NOT the structure validator — it reports config
version + required env keys. The structure findings ("custom_providers is a
dict") come from `validate_config_structure`. Reproduce and confirm your fix
with the exact checker, reading the live file:

    cd ~/.hermes/hermes-agent && HERMES_HOME=~/.hermes venv/bin/python3 -c \
      "import yaml; from hermes_cli.config import validate_config_structure; \
      [print(f'[{i.severity}] {i.message}') for i in validate_config_structure(yaml.safe_load(open('/home/moses/.hermes/config.yaml')))]"

No issue lines is the pass signal.

## Pitfalls

- **custom_providers must be a YAML list**, one entry per provider, each a dict
  carrying its provider id as a `name:` field (NOT as the mapping key). A
  corrupted form has the id as a dict key and leaks sibling fields
  (`base_url`, `api_mode`) to the section root — those leaked fields are often
  stale fallback-tier debris and should be dropped, not promoted into a fake
  list entry (a custom provider needs name + base_url + models; a bare
  base_url/api_mode pair is not one).
- **Before touching upstream, confirm the boundary.** If the finding's fix
  would modify `~/.hermes/hermes-agent/` source or node deps, that is
  NousResearch-owned — report it and stop. Config repair only touches
  `~/.hermes/config.yaml`.
- A section replacement list must match the schema the validator expects —
  confirm the entry field shape (e.g. `name:`, `base_url:`) against the
  validator's required-fields tuple before writing, so the fix clears the
  finding on the first validator run.
