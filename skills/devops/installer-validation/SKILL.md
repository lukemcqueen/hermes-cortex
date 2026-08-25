---
name: installer-validation
description: "Validate installers and strip post-decommission stale refs."
version: 1.0.0
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [installer, validation, stale-reference, decommission, deploy, sweep, orchestrator-gate]
    related_skills: [shell-scripting, repo-gotchas, deployed-component-verification, enforcement-change-safety]
---

# Installer Validation

When the repo's installers have been updated over time and a component was
decommissioned or renamed (real example: gbrain → mycortex, 2026-08-02),
run a class-level validation sweep before touching anything. This skill is
the checklist for "are the installers current and will they work" plus the
commit-gate reality that attends repo `ops/` work.

## When to Use

- User asks to "validate the installers", "make sure everything is current",
  or "remove stale components/dependencies"
- A component was decommissioned and installers still reference it
- Before shipping a change to `ops/install/`, `ops/scripts/install/`,
  any `install-*.sh`, `quick-start.sh`, or deploy templates
- Preparing installer work for orchestrator handoff from a non-orchestrator host

## Prerequisites

- The current host may be a non-orchestrator (e.g. `titus`). Commits to
  `ops/` are blocked by the pre-commit hook in that case — see the
  commit-gate section; the deliverable becomes a verified staged diff.

## Procedure

### 1. Survey the installer surface

Find every installer and its referenced script paths. `bash -n` every one
first — validates syntax before any semantic work.

```bash
bash -n ops/install/install.sh ops/install/quick-start.sh \
  ops/scripts/install/*.sh ops/scripts/install-crons.sh
```

Verify every path each installer references actually exists in the repo
(`_scripts()`, `_deploy()`, `_offline()`, `_core_gov()`, `${SCRIPT_DIR}`,
`${REPO_ROOT}` forms). Use a Python extraction pass rather than blind grep —
function-call forms (`$(_scripts)/...`) and quoted forms both appear.

### 2. Decommissioned-component sweep

Grep every location for the old name — do NOT stop at the obvious file:

```bash
for d in ops/install ops/install/deploy ops/scripts/install ops/scripts/health \
         ops/scripts/agent docs/install; do
  [ -d "$d" ] && grep -rni '<old-name>' "$d" 2>/dev/null
done
# also cortex-update.sh register/unregister blocks and
# cortex_doctor/checks.py (its remediation hints still name old units)
```

Classify each match:
- **Dead dependency (remove):** an install block that existed only for the
  old component and now uses a broken URL. Real case: the gbrain
  `ollama-linux-*.tgz` `llama-server` tarball extraction — the `.tgz` format
  is a 404 (became `.tar.zst`), and the replacement (mycortex) is pure Python
  needing no `llama-server`. Remove the whole block.
- **Compat logic (keep, relabel):** password-variable reuse
  (`GBRAIN_PG_PASSWORD` → `MYCORTEX_PG_PASSWORD`), legacy plugin-name checks
  in `config.yaml`, decommission comments. Keep these; only fix wording that
  claims the old component is installed/needed.

### 3. Remove orphaned deploy files only after proving zero refs

A stale template (`deploy/<old>-autopilot.service`) may be referenced by the
doctor or health scripts that detect the half-state on old hosts — those
reference the **systemd unit name**, not the repo file, and are correct to
keep. Prove the repo file is safe to delete:

```bash
grep -rn '<unit>' ops/scripts/cortex-update.sh ops/install/install.sh
# if nothing deploys/copies it → git rm is safe
```

### 4. Health-vector key drift — single source of truth

The `SERVICE_MAP` key list is duplicated across the live emitter
(`ops/scripts/health/health-vector.py`) and several consumers that must agree:
`agent-registry.template.json`, `agent-registry.json.example`,
`orch-fleet-watchdog.py`, `orch-health-report.py`, and the push script's
index comments. After any rename (e.g. `gbrain_sources_ok` →
`mycortex_sources_ok`) all five must match or the fleet watchdog/report misreads
the live vector. Treat the emitter's list as the authority and grep every copy
of the old key. Validate the JSON files still parse after edits.

### 5. Undefined `${SCRIPT_DIR}` in standalone helper installers

Small installers (`quick-start.sh`) sometimes reference `${SCRIPT_DIR}`
without defining it, so the skill/file-copy block silently no-ops (exit 0, no
error). Define it from `"${BASH_SOURCE[0]}"` and walk up to the repo root, and
drop from install lists any skill/path that no longer exists in the repo
(`find . -type d -name '<skill>'` returns nothing). Verify the copy actually
lands by running the script with a temp `HERMES_HOME` — running is the only
proof.

### 6. Verify

- `bash -n` every changed shell script
- PY syntax check changed `.py` files
- Run the changed `install.sh --check` from the real repo path (proves it
  executes end-to-end)
- Run the adversarial gate (A2 default; A4 for manage/quality/hooks) on every
  changed script
- targeted pytest on tests that touch the changed files
- PII scan (`secret-leak-detector.sh`)

### 7. Orchestrator-only commit gate

The pre-commit hook BLOCKS commits on `ops/` (and other
`docs/orchestrator-only-paths.txt` entries) by reading the COMMITTED config —
editing the working copy cannot bypass it, and `--no-verify` is a logged
governance violation. Non-orchestrators:

1. Do ALL validation on a branch first so the diff is commit-ready: `git
   checkout -b titus/<slug>`, apply changes, run the step-6 suite.
2. Stage, then run `git commit` ONCE to confirm the block fires (expected).
3. Deliverable is a **verified, staged diff for orchestrator handoff** (bus
   message / PR with the branch name), not a landed commit. Say so plainly in
   the delivery so the orchestrator knows it is validated and ready to commit.

## Pitfalls

- **Missing `SCRIPT_DIR`** — a copy/skill block silently no-ops; verify by
  running, not reading.
- **`.tgz` Ollama URLs** are dead — the release format became `.tar.zst`.
- **Don't grep only `ops/install/`** for a stale name — the same string lives
  in health scripts, agent orch scripts, doctor checks, and `cortex-update.sh`.
- **Orchestrator-only blocks are not bugs** — expect the commit to refuse on a
  non-orchestrator host and hand off with the stage intact.
- **Pre-existing test failures** (missing `yaml`, unrelated module import
  exit) should be confirmed unrelated to your diff before reporting.

## Verification

- All changed scripts pass `bash -n` and the adversarial gate
- The changed `install.sh --check` runs from the real path with no error
- If on a non-orchestrator host: changes staged on a branch, commit-verify
  attempted, handoff prepared
