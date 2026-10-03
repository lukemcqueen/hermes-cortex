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
`register "<repo path>" "<deployed path>"` calls — **335** of them at the time of
writing.

**The deployed path cannot be derived from the repo path.** Only 108 of the 335
follow the obvious "strip the leading `ops/`" rule. **227 follow no rule at all**,
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
`cortex_lib.paths.resolve_repo_resource()`, which reads the map. See
[`docs/repo-vs-deployed-paths.md`](repo-vs-deployed-paths.md).

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
that legitimate unlock window for a break — see `docs/troubleshooting.md` #24.

## Related

- [`docs/repo-vs-deployed-paths.md`](repo-vs-deployed-paths.md) — resolving a
  repo-relative sibling in both layouts
- [`docs/architecture.md`](architecture.md) — services and ports
- [`docs/fleet-update-protocol.md`](fleet-update-protocol.md) — fleet rollout
