# Deploy Registry Pattern

> **Rewritten 2026-10-03.** This document previously described a `legacy-brain/` +
> `private-data` multi-repo strategy with hermetic `cortex-profile.sh` profiles,
> `brain-*` branches and a private→public sync workflow. **None of that exists in
> this repository** — it was fabricated documentation. Every claim below was
> checked against the tree.

## Overview

Hermes Cortex deploys with **one repository and one explicit file map**:

```
hermes-cortex (repo)                        ~/.hermes-cortex (deploy)
        │                                            ▲
        └────── ops/scripts/cortex-update.sh ────────┘
                     register() map
```

There is **no private companion repository** and **no second remote**:

```bash
$ git remote -v
origin  https://github.com/lukemcqueen/hermes-cortex.git (fetch)
origin  https://github.com/lukemcqueen/hermes-cortex.git (push)
```

Branches are `main` plus topic branches (e.g. `session/gov-isolation`). There are
no `brain-*` branches, no `legacy-brain/` directory, and no `private-data/`.

## The register() map

`ops/scripts/cortex-update.sh` holds the deployment as data: a list of
`register "<repo path>" "<deployed path>"` calls — **360** of them (count
re-measured 2026-10-20;
`tests/test_repo_resource_paths.py` computes all three numbers below, so change
the doc in the same commit as any `register()` edit).

**The deployed path cannot be derived from the repo path.** Only 122 of the 360
follow the obvious "strip the leading `ops/`" rule. **238 follow no rule at all**,
and every one of those also drops a subdirectory:

| repo | deployed |
|---|---|
| `ops/scripts/manage/task-db.py` | `scripts/task-db.py` |
| `ops/scripts/health/heartbeat.py` | `scripts/heartbeat.py` |
| `ops/scripts/install/check-system.sh` | `scripts/check-system.sh` |
| `ops/scripts/cortex_gateway/daemon.py` | `scripts/cortex_gateway/daemon.py` |
| `ops/services/mycortex-mem/context_tools.py` | `services/mycortex-mem/context_tools.py` |

Two files under `ops/scripts/manage/` deploy to different depths. **Never guess a
deployed path and never write a candidate list** — call
`cortex_lib.paths.resolve_repo_resource()`, which reads the map — see the
**Repo-vs-Deployed Path Resolution** section at the end of this file.

## The generated manifest

Because the mapping is data, the deploy writes it out. Every sync emits:

```
${CORTEX_DEPLOY_HOME}/deploy-manifest.tsv
# repo-relative path<TAB>deployed path
ops/scripts/manage/task-db.py	/home/<user>/.hermes-cortex/scripts/task-db.py
```

It is **generated, never hand-edited**, and lives at the deploy root rather than
under `scripts/`, so the orphan sweep does not remove it. Read it with
`cortex_lib.paths.deploy_manifest()`.

## Adding a file

1. Add the file to the repo.
2. Add a `register` line in `ops/scripts/cortex-update.sh` — **repo path first,
   then deployed path**.
3. `bash ops/scripts/cortex-update.sh`
4. Verify on the **deployed** tree, not the repo.

Step 2 is not optional. The deploy syncs an explicit list, so a file that is
imported but never registered ships as an `ImportError` on the host **while the
repo tests stay green** — the repo tests import the repo tree, which always has
the file. `tests/test_gateway_modules_are_deployed.py` fails the build when the
register list and a package directory disagree.

## Environment

The canonical env is the **repo** env:

```
~/hermes-cortex/.env        mode 600 — the one file to edit
```

Units read it via `EnvironmentFile=-%h/hermes-cortex/.env`. Do not invent variable
names: the deploy and the units reuse the same names Hermes uses
(`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `TELEGRAM_HOME_CHANNEL`, …).

## Repository layout

```
hermes-cortex/
├── core/            cortex_bus, governance — shared runtime libraries
├── docs/            this document, design docs, runbooks, templates/
├── evals/           evaluation harnesses
├── laptop/          workstation-specific tooling
├── mcp-servers/     the MCP servers every agent connects to
├── ops/
│   ├── deploy/      deploy helpers
│   ├── install/     installers (cortex-profile.sh, bootstrap-brain.sh, …)
│   ├── offline/     offline content tooling
│   ├── scripts/     cortex-update.sh, cortex_lib/, health/, manage/, …
│   ├── services/    long-running services (mycortex-mem, …)
│   └── web-cache/   web cache tooling
├── plugins/         Hermes plugins (governance-enforcer)
├── profiles/        profile docs (README only — NOT per-project toolchains)
├── skills/          agent skills
└── tests/           pytest suite
```

`ops/scripts/install/cortex-profile.sh` **does** exist, but it is not the hermetic
per-project toolchain loader the previous version described: `profiles/` contains a
README, not `profiles/<name>/` directories with `activate`/`deactivate` hooks and
pinned `tools/`.

## Operations

```bash
# Deploy — syncs the register map and relocks the enforcement files
bash ops/scripts/cortex-update.sh

# Pre-push gate: pull → deploy → doctor → verify
bash ~/.hermes-cortex/scripts/cortex-dogfood.sh --force

# Verify what actually landed
cat ~/.hermes-cortex/deploy-manifest.tsv
hermes-plugin-lock status
```

`cortex-update.sh` unlocks the immutable enforcement files early and **relocks them
in its EXIT trap**, so even a failed run leaves the gate locked. It also publishes
`state/deploy-in-progress` for the duration, so a periodic auditor does not mistake
that legitimate unlock window for a break — see `docs/troubleshooting.md` -> *"Doctor reports PENDING cycles left by other sessions"*.

## Related

- *Repo-vs-Deployed Path Resolution* (below) — resolving a repo-relative sibling in both layouts
- [`docs/architecture.md`](architecture.md) — services and ports
- [`docs/fleet-update-protocol.md`](fleet-update-protocol.md) — fleet rollout

---

## Repo-vs-Deployed Path Resolution

> **Merged from `docs/repo-vs-deployed-paths.md` on 2026-10-20.** These two documents covered two halves of one topic; the section below is the half that lived in `docs/repo-vs-deployed-paths.md`. That source path is preserved in git history and recorded in [`docs/older/README.md`](older/README.md) — no content was dropped in the merge.

**Applies to:** any component that loads a sibling file from the repo — every MCP
server, every `ops/scripts/` tool, every harness adapter.

### The problem

The repo and the deploy are **not** the same tree. `cortex-update.sh` copies files
to `${CORTEX_DEPLOY_HOME}` (normally `~/.hermes-cortex`) and the mapping is
**per-file**:

| repo | deployed |
|---|---|
| `ops/scripts/manage/task-db.py` | `scripts/task-db.py` |
| `ops/scripts/manage/agent-no-verify-audit.py` | `scripts/manage/agent-no-verify-audit.py` |
| `ops/scripts/judgment.py` | `scripts/judgment.py` |
| `ops/offline/hermes_paths.py` | `offline/hermes_paths.py` |

Of the same 360 `register()` calls, **238 follow no derivable rule** — the first two rows
above both live under `ops/scripts/manage/` and deploy to different depths.

So a component that *guesses* — strip `ops/`, strip a subdir, try a short list of
candidates — resolves fine in the repo and then **fails after a deploy, on a host,
far from the edit**. That is the bug class this document exists to end. It is not
hypothetical: `loop-gov-mcp.py` guessed `<deploy>/tools/ops/scripts/judgment.py`,
a path that exists in *neither* layout.

### The rule

**Never derive the deployed path. Never hand-roll a candidate list. Call the one
resolver.**

```python
## ── cortex_lib bootstrap — IDENTICAL in every MCP server; do not vary. ─────
## cortex_lib/paths.py sits in the scripts dir in BOTH layouts (ops/scripts/
## in-repo, scripts/ deployed), so locate it by that dir rather than by guessing a
## relative depth. Guarded on purpose: the import failure is reported by whichever
## server actually needs the resource, naming what it wanted.
resolve_repo_resource = repo_resource_candidates = None
for _p in Path(__file__).resolve().parents:
    if (_p / "cortex_lib" / "paths.py").is_file():
        sys.path.insert(0, str(_p))
        break
try:
    from cortex_lib.paths import (  # noqa: E402
        repo_resource_candidates, resolve_repo_resource)
except ImportError:
    pass

_RESOURCE_REL = "ops/services/mycortex-mem/context_tools.py"
_resource = resolve_repo_resource(_RESOURCE_REL) if resolve_repo_resource else None
if _resource is None:
    _tried = ([str(p) for p in repo_resource_candidates(_RESOURCE_REL)]
              if repo_resource_candidates else ["<cortex_lib.paths unavailable>"])
    print(f"[my-server] ERROR: {_RESOURCE_REL} not found. Tried: "
          + ", ".join(_tried), file=sys.stderr)
    sys.exit(1)
```

Three properties, each with a test that enforces it
(`tests/test_repo_resource_paths.py`):

1. **The bootstrap is byte-identical in every MCP server.** Per-server variants are
   how the servers drifted apart in the first place.
2. **The repo-relative path is a named `_…_REL` constant**, handed to the resolver,
   so the lookup and the error message cannot disagree about what was wanted.
3. **A miss is loud.** `repo_resource_candidates()` reports *where* it looked. A
   silent skip turns a broken component into a mysterious absence.

### How it resolves

`resolve_repo_resource(rel)` tries, in order:

1. **Repo layout** — `<repo>/rel`, for each ancestor holding `ops/scripts/`.
2. **Deployed layout** — the entry for `rel` in `deploy-manifest.tsv`.

There is no step 3. It does not strip prefixes, and it does not guess.

### The manifest

`cortex-update.sh` already holds the mapping as data (its `register()` map), so it
**writes it out** to `${CORTEX_DEPLOY_HOME}/deploy-manifest.tsv` on every sync:

```
## GENERATED by cortex-update.sh from its register() calls — do not edit.
## repo-relative path<TAB>deployed path
ops/scripts/manage/task-db.py	/home/esther/.hermes-cortex/scripts/task-db.py
```

One source of truth: the `register()` lines. The manifest is generated, never
maintained by hand, and it lives at the deploy root (not under `scripts/`), so the
deploy's orphan sweep does not remove it.

Read it with `cortex_lib.paths.deploy_manifest()` (walk-up) or
`read_manifest(path)` (explicit path — use this in tests, since the repo has no
manifest of its own and a walk-up lookup would always skip there).

### Related

- `docs/troubleshooting.md` -> *"Doctor reports PENDING cycles left by other sessions"* — the deploy's immutable-flag unlock window and the
  auditor that samples inside it.
- `docs/deploy-registry-pattern.md` — the real deployment: the `register()` map, the
  generated `deploy-manifest.tsv`, and how to add a file.
