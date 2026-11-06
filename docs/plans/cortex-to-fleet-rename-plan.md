# Plan — `cortex-` short-name rename (`cortex-*` / `cortex_*` / `CORTEX_*` → `fleet-*`)

> **Status:** PLAN — not started. **Boundary and scope are decided** (operator decisions §*decisions*
> below, recorded 2026-11-06: staged not bang · dashboard joins as `fleet-dashboard` · names-only
> with `CORTEX_*` env vars deferred · `hermes-cortex*` skills deferred to a third sweep). P0 begins
> once this plan is approved.
> **Author:** Esther (orchestrator). **Governance cycle:** #14235.
> **Predecessors:** the `hermes-cortex` → `steadfaste-fleet` sweep (2026-11-04, 938 files) and the
> `hc-` prefix drop (`aa03092f`, 2026-11-06). Both left the **`cortex` short-name family** in place
> on purpose — see `docs/rename-followups-steadfaste-fleet.md`, §*"The `cortex` short-name family is
> a SEPARATE naming layer (not covered)"*. This document is that second sweep.

## Operator decisions (2026-11-06) — locked in

| # | Question | Decision | Effect on this plan |
|---|---|---|---|
| Q1 | Why was the 2026-11-04 attempt reverted? | **It was too big a bang** — the failure was execution size, not design. The boundary still holds. | Staged §5 confirmed; the §3 boundary stands unchanged (that is what a bang got wrong, so the plan stays split). |
| Q2 | Does the dashboard unit join the rename? | **Yes.** `hermes-cortex-dashboard` → **`fleet-dashboard`** (kept `-dashboard`, dropped the `hermes-cortex` product prefix to match the rest of the framework's `fleet-` family). | §3.1 now sweeps the dashboard service + plist; the §3.3 contradiction is resolved. |
| Q3 | Full sweep (incl. env vars) or names-only? | **Names-only.** `CORTEX_*` env vars are **deferred** to a follow-on release. | §6's primary recommendation flips to names-only (≈ 6,735 executable); §5 P4 is retained as the *deferred* env-var change, not part of this sweep. |
| Q4 | Fold the four `hermes-cortex*` skills now? | **Leave for a third sweep.** | §3.3 keeps them excluded; this plan does not touch their `name:` load key. |

---

## 1. Goal

Retire the last framework-wide brand straggler: the short name `cortex` (in its `cortex-`,
`cortex_`, `CORTEX_`, `Cortex` spellings) used as the *framework's own* identifier, replacing it
with `fleet`. After this lands, the only surviving `cortex` tokens in the repo are the deliberate
exceptions enumerated in §3.

**Non-goal:** the `mycortex` knowledge-brain product — a different product with its own database,
schema, roles and CLI. Out of scope (§3.2).

---

## 2. Measured scope

Computed 2026-11-06 over `git ls-files` (3,517 tracked files), compiled caches skipped.

> **Evidence (committed in this cycle, re-runnable):**
> `docs/evidence/cortex-to-fleet-scope-2026-11-06.py` + `.txt` — emits §2, §4.2 and §9 item 2 verbatim.
> `docs/evidence/cortex-to-fleet-worktree-2026-11-06.sh` + `.txt` — emits §4.7 and §4.8 verbatim.
> Both are READ-ONLY and are run from the repo root. Each `.txt` is the captured stdout of its
> sibling script, recorded at `HEAD = 36670678` with `origin/main` at the same sha.
>
> **Every figure in this document is from that one run.** The `sweep` column is the number this
> sweep may rewrite: it excludes the *records* (`docs/older/`, `docs/evidence/`, `tests/artifacts/`,
> `docs/reviews/`), the **documents that describe this change** (this plan and its four evidence
> files mention the very tokens being counted, so including them would make each figure grow every
> time the plan is rewritten), and the four **Q4-deferred** `hermes-cortex*` skill dirs (they stay
> byte-identical; a third sweep owns them). The exclusion list is printed in the evidence §3.

| token family | total (all files) | files | **sweep** (this sweep) |
|---|---:|---:|---:|
| `cortex-` (hyphen) | 6,585 | 1,022 | 3,676 |
| `cortex_` (underscore) | 2,588 | 582 | 2,056 |
| `CORTEX_` (env / const) | 3,421 | 492 | 3,110 |
| `Cortex` (title case) | 421 | 174 | 211 |
| `\bcortex\b` (bare word) | 4,071 | 662 | 792 |
| **sweep-scope total** | | | 9,845 |
| *of which `CORTEX_*` (deferred, Q3)* | | | *3,110* |
| **names-only execution set** | | | **≈ 6,735** |

Tracked paths whose name contains `cortex` (excluding `mycortex`): **198**, of which **67** are
excluded → **131 sweep paths** to rename.

Bare-`cortex` is concentrated in record directories; the sweep-scope bare-word count is only 792.

### 2.1 Densest sweep-scope carriers (measured)

```
 817  ops/scripts/cortex-update.sh                 (register() map — governance-critical)
 379  ops/scripts/manage/cortex_doctor/checks.py
 227  ops/install/install.sh
  94  tests/test_skills_ownership.py
  79  mcp-servers/loop-gov-mcp.py
```

`ops/scripts/cortex-update.sh` holds **388** `register`/`register_orch` map entries (346 +
42) — the single densest file and the governance-critical one (§4.1). See §9 item 2 for the
count reconciliation (383 test-visible, 5 `${HOME}/` shapes, 445 token occurrences).


---

## 3. The boundary — what is renamed, what is deliberately kept

`grep` is not a specification. This section **is** the specification; the sweep's ordered guard
table is derived from it verbatim.

### 3.1 RENAME — the framework's own identifiers

| Layer | From | To |
|---|---|---|
| Python packages | `cortex_bus`, `cortex_lib`, `cortex_doctor`, `cortex_gateway` | `fleet_bus`, `fleet_lib`, `fleet_doctor`, `fleet_gateway` |
| Deploy script | `ops/scripts/cortex-update.sh` | `ops/scripts/fleet-update.sh` |
| Scripts / modules | `cortex-doctor.py`, `cortex-health.sh`, `cortex-dogfood.sh`, `cortex-context.py`, `cortex-sandbox.py`, `cortex-agent-manager.py`, `cortex-bus-bridge-*.py`, `cortex-bus-mcp.py`, `cortex-context-mcp.py`, `cortex-sandbox-mcp.py`, `cortex-bus-processor.py`, `cortex-bus-remediate.sh`, `cortex-bus-failover-watchdog.py`, `cortex-profile.sh`, `fix-cortex-venv.py`, `setup-cortex-bus.sh`, `install-cortex-update-cron.sh`, `cortex-update-mutex.py`, `cortex-setup-langfuse.sh` | same with `fleet-` / `fleet_` |
| Config / unit templates | `ops/install/deploy/config/cortex-config.yaml`, `ops/install/deploy/cortex-bus.service`, `hermes-cortex.env.example`, `docs/templates/cortex-gateway.service`, `docs/templates/com.hermes.cortex-gateway.plist`, `com.hermes.cortex-dashboard.plist`, `ops/services/dashboard/com.hermes.cortex-dashboard.plist` | `fleet-*` / `com.steadfaste.fleet-dashboard.plist` |
| Pi-harness extensions | `cortex-context.ts`, `cortex-governance.ts` | `fleet-context.ts`, `fleet-governance.ts` |
| Env vars (`CORTEX_*`) | **DECIDED (Q3): outside this sweep.** 138 distinct names / 3,097 identifier occurrences / 3,110 family occurrences (§4.2) — deferred to a follow-on release, §5 P4 spec-only | not renamed here |
| systemd units | `cortex-bridge-*` (~90 service + timer + `.wants`), `cortex-bus.service`, `cortex-gateway.service`, `cortex-gateway-<agent>.service`, `hermes-cortex-dashboard.service` (Q2) | `fleet-bridge-*`, `fleet-bus`, `fleet-gateway`, `fleet-dashboard` |
| Cron names (`~/.hermes/cron/jobs.json`) | `cortex-bus-workday`, `cortex-bus-evening`, `cortex-bus-overnight` | `fleet-bus-workday`, `fleet-bus-evening`, `fleet-bus-overnight` |
| Skill load keys | `cortex-bus`, `cortex-bus-automation`, `cortex-bus-inbox`, `cortex-bus-messaging`, `cortex-bus-polling`, `cortex-preflight`, `cortex-deployment-sync` | `fleet-bus*`, `fleet-preflight`, `fleet-deployment-sync` |
| Live docs | `docs/design/cortex-gateway.md`, `cortex-gateway-parity.md`, `cortex-memory-session-mcp.md`; `docs/runbooks/cortex-env-migration.md` | `fleet-*` |
| Prose | `Cortex` / `cortex` where it names the framework | `Fleet` / `fleet` |

### 3.2 KEEP — `mycortex` is a different product

`mycortex` is the knowledge brain; its `cortex` is a substring of a **different word**. Never
match it, never "fix" it, never rename its `cortex` half:

- PG: database `mycortex`, roles `mycortex` / `mycortex_admin`, schema `mycortex.*`
  (`ops/services/mycortex/schema/mycortex.sql`). `CORTEX_BUS_PG_DB` **defaults to** the value
  `mycortex` (`core/cortex_bus/queue.py:28`). Neither renames in THIS sweep: the VALUE stays
  `mycortex` (this section), and the variable NAME stays `CORTEX_BUS_PG_DB` until the deferred P4
  env-var change (Q3) — **this note must not be read as permission to sweep `CORTEX_*` now.**
- `plugins/mycortex-mem/`, `plugins/mycortex-command/`, `ops/services/mycortex-mem/`,
  `ops/services/mycortex/`, `ops/install/deploy/docker-compose.mycortex.yml`
- `mycortex` CLI, `mycortex-parity.py`, `agent-mycortex-sync.sh`, `agent-mycortex-retention.py`
- `agent-mycortex-dream-*` crons; `skills/devops/mycortex/`; `docs/design/mycortex-*.md`

> **Guard rule (first guard in the ordered pass, before any case-preserving catch-all):** every
> replacement regex on `cortex` carries a **double negative lookbehind** —
> `(?<!my)(?<!hermes-)cortex`. The `my` half keeps `mycortex` (the §3.2 brain) intact; the
> `hermes-` half keeps the four `hermes-cortex*` skill names and the enforcer's
> `(hermes-cortex|steadfaste-fleet)` accept list intact (§3.3) — **without it, a bare
> `cortex`→`fleet` replace silently rewrites `hermes-cortex` into `hermes-fleet`**. The deliberate
> `hermes-cortex` consumers that DO join this rename are renamed by explicit targeting rules
> (mapping lines in §5 P3/P5), never by the catch-all:
> - `hermes-cortex-dashboard.service → fleet-dashboard.service` (§5 P5)
> - `ops/install/deploy/hermes-cortex.env.example → ops/install/deploy/fleet.env.example`
>   (§5 P3)
> **Post-condition:** `git grep -c mycortex` is **unchanged per file**, and `git grep -c
> hermes-cortex` is unchanged **except for the deliberately-repointed artifacts** — the dashboard
> unit, `hermes-cortex.env.example` (path and any content references the mapping touches), and the
> per-host transition tooling (same counts before and after) — this is the assertion that proves
> §3.2 and §3.3 held.

### 3.3 KEEP — decided by the operator (2026-11-06), this sweep does not touch them

- Skill dirs + `name:` frontmatter for `hermes-cortex`, `hermes-cortex-setup`,
  `hermes-cortex-maintenance`, `hermes-cortex-repo-deploy` — the `skill_view(name=...)` load key.
  **Q4: deferred to a THIRD sweep**; do not fold them in here.
- The enforcer's dual-URL accept list `(hermes-cortex|steadfaste-fleet)`.
- **Q2 resolved:** the dashboard is **not** a kept exception — `hermes-cortex-dashboard.service`
  joins this rename as `fleet-dashboard.service` (the earlier 2026-11-04 follow-ups doc that said
  "keeps its name" is superseded by the operator decision for this artifact).
  This doc's §3.1 sweeps it.

### 3.4 KEEP — records and self-referential tools

**Record rule (mechanical, no judgement):** a path is a *record* if it lives under `docs/older/`,
`docs/evidence/`, `tests/artifacts/` or `docs/reviews/`, **or** its filename carries a date. A
record quotes the old name as the thing that WAS there at that revision; rewriting it falsifies
the record and breaks the checksum it carries. Records are excluded from the replacement pass
**and** the residue grep — and the exclusion list is printed beside the count, because a bare
"0 residuals" that silently skipped a directory over-claims.

**Self-referential tools (must keep the old literal — a blanket replace inverts them):**
- The migration tool itself (`migrate-cortex-to-fleet.sh`): its idempotency check depends on the
  old name.
- **One-release compat/forwarding shims** (transient by design): the `cortex_<pkg>/__init__.py`
  re-export shims (§5 P2) and `ops/scripts/cortex-update.sh` forwarding shim (§5 P3) must keep the
  old token — that is their job. They are excluded from the §7 residue grep while the release
  window they serve is open, and are deleted (with their residue fully swept) in the "remove the
  shim" follow-on commit. List them in the sweep's commit message so a later reader does not
  "finish" the relocation on them.
- Detection/report messages whose *subject* is the old name (doctor "stray …", enforcer brand
  allow-list entry) — the old name is the SUBJECT of the sentence, not a path to resolve.
- `docs/rename-followups-steadfaste-fleet.md`, `docs/runbooks/fleet-local-dir-rename.md`,
  **this plan** and the P0-created `docs/rename-cortex-to-fleet.md` — a path-token replace rewrites
  both sides of their `old → new` mapping lines, inverting them to `new → new` and silently
  deleting the worked example. (Measured pitfall: `rename-sweep`'s own worked example was corrupted
  exactly this way.) The P0 boundary doc is added to §3.4/mapping exclusions when it is created,
  in the same commit.
- `docs/images/hermes cortex avatar.jpg` — a binary asset; rename only with its doc references.

---

## 4. Runtime-contract surface — the risk register

This is why the rename is not a `sed`. Each item is a live contract a host depends on.

### 4.1 🔴 Governance-critical — the deploy command is sanctioned by its literal path

`plugins/governance-enforcer/__init__.py` classifies `cortex-update.sh` as **write-class** and
sanctions exactly one invocation:

```python
# plugins/governance-enforcer/__init__.py:2013
r"^\s*(?:bash\s+)?(?:~|" + re.escape(str(Path.home())) +
    r")/(?:hermes-cortex|steadfaste-fleet)/ops/scripts/cortex-update\.sh"

# plugins/governance-enforcer/__init__.py:2018
def _is_sanctioned_cortex_update_command(command: str) -> bool:
```

**Rename the script without editing this literal and every host's deploy command becomes an
unsanctioned write-class command — the fleet can no longer deploy.** This is the highest-risk
coupling in the sweep and the reason §6 recommends a shim over a hard rename.

Same file, further couplings: `cortex_doctor/` module paths ("MUST stay in sync", lines 487, 495);
deploy-reload comments (142, 829, 3280, 3312–3319).

### 4.2 🔴 Env vars live outside the repo

**138 distinct** `CORTEX_*` identifier names, **3,097** occurrences (sweep scope, same run as §2).
Two counters exist and they are **deliberately different measurements — never mix them in one
claim**. Both are reported in the evidence §7 from the same run:

| counter | regex | sweep | what it is for |
|---|---|---:|---|
| family | `CORTEX_` | 3,110 | needed LATER (P4) — catches prose wildcard mentions too |
| identifier | `CORTEX_[A-Z0-9_]+` | 3,097 | needed LATER (P4) — real names only |

The **13-token delta** is `CORTEX_` followed by a character that cannot continue an identifier —
measured, every one is a **prose wildcard mention** written `` `CORTEX_*` `` in docs
(`docs/DOCS-INDEX.md:79`, `docs/env-vars.md:3`, …), not an env var name. **Nothing here is swept
in P0–P7** (Q3); these counters exist so the deferred P4 executes with the right tool for each job.

The **values** live in files a repo sweep cannot touch: `~/.steadfaste-fleet/.env`,
`~/.steadfaste-fleet/agent.env`, systemd `Environment=` / `EnvironmentFile=`, nginx site configs
(`CORTEX_NGINX_PORT_PREFIX`, `CORTEX_DOMAIN`), the Pi-harness manifests, and every peer host's own
`.env`. Top carriers (measured, same run):

```
673 CORTEX_DEPLOY_HOME      450 CORTEX_REPO          224 CORTEX_HOME
178 CORTEX_BUS_URL          120 CORTEX_BUS_TOKEN     111 CORTEX_SESSION_REPO
 91 CORTEX_BASIC_AUTH        87 CORTEX_BUS_FALLBACK_URL
```

A repo-only rename of these produces a **silent** fall-through to defaults (`CORTEX_DEPLOY_HOME`
unset ⇒ the deploy targets the wrong home). Requires dual-read — §5 P4.

### 4.3 🟠 systemd unit names are not all deploy-generated

`cortex-bus-bridge-generate.py` regenerates the ~90 `cortex-bridge-*` units. It does **not** write
`cortex-bus.service`, `cortex-gateway.service`, `cortex-gateway-<agent>.service` or the dashboard
unit — those are hand-installed and must be hand-migrated per host. (Documented pitfall: the
golden-path unit scan stays red until they are rewritten.)

### 4.4 🟠 Python packages are imported by everything

`cortex_bus`, `cortex_lib`, `cortex_doctor`, `cortex_gateway` are imported by MCP servers, the
enforcer plugin, git hooks, crons and tests. `cortex_lib/paths.py` is the *resolver* every MCP
server bootstraps from by walking parents for `cortex_lib/paths.py` — renaming the package without
renaming that walk breaks every MCP server at once.

### 4.5 🟠 Skill names are gate keys

`cortex-bus`, `cortex-preflight`, `cortex-deployment-sync` and friends appear as string literals in
the enforcer's domain-skill gate (`_PATH_CTX_HINTS`, `_EXT_DOMAIN_SKILLS`,
`_FILENAME_DOMAIN_SKILLS`), the pre-commit ritual loop, `reflexion-check.py`'s `DEFAULT_SKILL`,
`skills.yaml` (line 53), `docs/SKILLS-MANIFEST.md`, and `docs/guardrail-registry.json`
`restraint: skill:<old>`. A missed literal bricks a whole write class permanently.
**Sequencing rule:** the new skills must exist, be committed, deployed and *loaded* **before** the
commit that flips the gate names.

### 4.6 🟠 MCP / harness manifests outside the repo

`~/.hermes/config.yaml` `mcp_servers.*.args` points at
`~/.steadfaste-fleet/scripts/cortex-bus-mcp.py` (measured line 254); the Pi manifest
`~/.pi/agent/mcp.json` points at `cortex-context-mcp.py` and registers a server literally named
`cortex-context`. The five Hermes-side registration names are already clean (`agent-bus`, `tasks`,
`executor`, `review`, `loop-governance`). `config.yaml` is security-sensitive — repoint with
`hermes config set`, never a file write.

### 4.7 🟡 Prior-attempt residue — measured, must be cleared first

A partial `cortex` → `fleet` attempt ran on **2026-11-04** and was largely rolled back, leaving
orphans that are still on disk (measured by `cortex-to-fleet-worktree-2026-11-06.sh` §4):

```
core/fleet_bus/                    tracked files: 0   non-ignored untracked: 0   Nov 4 10:04
                                   (holds __pycache__/ + workflow/ — gitignored caches only)
ops/scripts/manage/fleet_doctor/   tracked files: 0   non-ignored untracked: 0   Nov 4 10:04
                                   (holds __pycache__/ only)
ops/scripts/fleet/                 tracked files: 7   — the LIVE new-name package, NOT residue
                                   (fleet.py, harness.py, bin/, .env.example)
```

So the residue is **two empty directory shells holding only gitignored bytecode**. Removing them is
safe (nothing tracked, nothing reachable), and it should happen in P0 so the sweep's own
construction-greps are not confused by a phantom `fleet_bus` path.

Deployed-side residue is named in `docs/runbooks/fleet-local-dir-rename.md` §4:
`~/.steadfaste-fleet/scripts/{fleet-doctor.py, fleet-update.sh, fleet_doctor, nightly-handoff.py}`
listed as `⚠ Stale deploy … not in any register() mapping`.

Measured: `git log --all -- ops/scripts/fleet-update.sh` → **0 commits**, while
`git log --all -- ops/scripts/cortex-update.sh` → **471 commits**. So `fleet-update.sh` was only
ever a host artifact, never a committed source. **Why it reverted (operator, §"decisions" Q1): it
was too big a bang — execution size, not design. The staged §5 approach is the correct response.**

### 4.8 🟡 In-flight uncommitted work in the working tree

Measured (`cortex-to-fleet-worktree-2026-11-06.sh` §1–§3), at
`HEAD = 36670678 = origin/main`:

```
D  ops/scripts/hc-plan-review-check.py
D  ops/scripts/hc-reflexion-check.py
D  plugins/hc-lean-index/__init__.py
D  plugins/hc-lean-index/plugin.yaml       4 files, 670 deletions — staged, uncommitted
```

All four paths are **still present in `HEAD`** — `ops/scripts/reflexion-check.py` and
`ops/scripts/plan-review-check.py` were *added* by `aa03092f` while the `hc-` originals were left
behind, so the repo currently carries both names for two gate scripts and one plugin.

Two honest caveats, because the mechanism is *not* proven by this evidence:

1. The obvious explanation is the documented rename-sweep pitfall (`git diff --cached --name-only`
   collapsing renames to their **new** path, so a pathspec commit leaves the deleted sources
   staged). **That is a hypothesis, not a measurement** — in this tree
   `git diff --cached --name-only` and `--name-only --no-renames` return the *same* four paths, so
   the collapse did not reproduce here. The cause needs `aa03092f`'s invocation from the session
   record before it is asserted.
2. The provenance claim ("same session lineage, not a peer's edit") rests on the authorship of the
   last commit (`esther-agent`) and the shared governance session lineage — **not** on a
   per-file attribution. Treat it as probable, and confirm with Moses before P0 rewrites anything.

Either way the operative point holds: this must be landed, with `git status` clean, **before** the
sweep starts. A dirty index corrupts every staged-path list the sweep depends on.

---

## 5. Phases

Ordered so the **deploy path keeps working at every commit** — the deploy is how the next phase
lands. Each phase is its own governance cycle + commit, deploys clean, and has an exit criterion
that is *observed*, not asserted.

### P0 — Prerequisites and freeze
1. Land the staged `hc-` deletions correctly:
   `git diff --cached --name-only --no-renames` → pathspec commit → verify
   `git ls-tree HEAD -- ops/scripts/hc-reflexion-check.py` is **empty** and `git status` clean.
2. Clear §4.7 residue (repo orphans + deployed stale files); record before/after counts.
3. **Decisions recorded** (done 2026-11-06): the four operator answers are the §*decisions* table
   at the top of this plan — no further history hunt is needed for Q1.
4. **Boundary doc committed** = this plan itself. A short `docs/rename-cortex-to-fleet.md` (the §3
   boundary + ordered guard table, in the `rename-followups` pattern) is cut from it and indexed in
   `docs/DOCS-INDEX.md`, so a later reader does not re-touch the kept names.
5. **Reconcile the `register()` figures** — DONE 2026-11-06: 388 map entries (346 + 42), 383
   test-visible, 5 `${HOME}/` shapes, 445 tokens. Recorded in §9 item 2; the previously-stale
   386 figure is corrected in `docs/deploy-registry-pattern.md` and its test is green. Sweep
   base = **388**.
6. Freeze: no concurrent rename in flight anywhere on the fleet; one owner.

**Exit:** index clean; residue count 0; boundary doc committed; the four decisions recorded and
greppable; the register-count base settled and recorded.

### P1 — Non-runtime prose and live doc paths
README, AGENTS.md, CLAUDE.md, CONTRIBUTING.md, `docs/` prose, and the live design/runbook/template
*filenames* from §3.1. No runtime contract — this is the shakedown of the replacement engine and
its mangle scan before anything load-bearing is touched.

**Exit:** residue grep 0 in scope; `docs/DOCS-INDEX.md` links resolve; `pre-commit-doc-audit.sh`
passes.

### P2 — Python packages, deepest dependency first
`cortex_lib` → `fleet_lib` (including the `cortex_lib/paths.py` parent-walk bootstrap, which is
byte-identical in every MCP server), then `cortex_bus`, then `cortex_doctor`, then `cortex_gateway`.

Each package ships a **one-release compat shim**: a `cortex_<pkg>/__init__.py` re-exporting from
`fleet_<pkg>` (and the reverse for the resolver walk). Ship shim + new package in the *same*
commit; delete the old package a release later, once `git grep` proves nothing imports it.

**Exit:** `py_compile` all changed; affected pytest modules pass; a **deployed-tree** import
(`python3 -c "import fleet_lib.paths"` run from `~/.steadfaste-fleet`) succeeds; MCP servers spawn
and answer.

### P3 — File/script names, `register()` map, sanctioned-command regex
The phase that must not break the deploy chain.
1. Widen the enforcer regex + `_is_sanctioned_cortex_update_command` to accept **both** names
   (the `(hermes-cortex|steadfaste-fleet)` dual-accept pattern), in its own commit, deployed and
   **verified by exercising both the old and the new deploy invocation**.
2. `git mv ops/scripts/cortex-update.sh ops/scripts/fleet-update.sh`; keep a `cortex-update.sh`
   **forwarding shim** for one release; update all **388** `register`/`register_orch`
   deployed-path targets (§9 item 2 — base settled as 388 in P0) and every caller
   (`cortex-dogfood.sh:23`, `pre-push-pull`, `install-crons.sh`, `install-cortex-update-cron.sh`,
   the bridge generator, the doctor's expected lists).
3. Sweep the remaining script/module filenames from §3.1, including the mapping lines the guard
   names — `ops/install/deploy/cortex-bus.service → fleet-bus.service`, the config/plist/template
   paths, and `ops/install/deploy/hermes-cortex.env.example → fleet.env.example` (these are
   explicit mapping rules, not the catch-all).

**Exit:** `bash -n` all; the deploy runs **from the new name** on a host (RC=0, doctor 0 fail);
the old name still works via the shim; `tests/test_repo_resource_paths.py` passes (it computes the
register-map numbers).

### P4 — Env vars `CORTEX_*` → `FLEET_*`, dual-read — ⏸️ **DEFERRED (operator Q3) — spec only**

> **Not part of this sweep.** Kept as the specification for a follow-on release. **Nothing in P4
> runs now**; the phase below is written so it can be executed intact later, with the same compat
> discipline, once the names-only sweep (and the third `hermes-cortex*` skills sweep) have landed.
>
> - When executed, it follows §4.2's two-counter rule (§7 of the evidence) — the family counter
>   drives the replacement, the identifier counter drives the inventory, and `CORTEX_*` reads stay
>   live until every host config is repointed.
1. One resolver helper reads `FLEET_X` then falls back to `CORTEX_X` with a **loud** one-time
   deprecation warning — never silent, because a silent fallback is exactly how a half-migrated
   host hides.
2. Sweep call sites onto the helper; rename the literal names in repo-owned files.
3. **Per host, before the fallback is removed:** repoint `.env`, `agent.env`, systemd
   `Environment=`, nginx configs, harness manifests.
4. Release 2 removes the fallback and the `CORTEX_*` names.

**Exit:** every var in the doctor's `--json` env audit resolves from its `FLEET_` name; the
deprecation warning is observed exactly once per host; no host has an unset `FLEET_DEPLOY_HOME`.

### P5 — systemd units, cron names, bridge units
1. Regenerate the deploy-generated `cortex-bridge-*` units from the manifest.
2. Hand-migrate the non-generated units (`cortex-bus`, `cortex-gateway`,
   `cortex-gateway-<agent>`, and `hermes-cortex-dashboard` → `fleet-dashboard` per decision Q2):
   `disable` old → `enable` new →
   `daemon-reload` → drop the old `.wants` symlink. Keep the old unit files on disk, disabled.
3. Rename the `cortex-bus-*` crons in `jobs.json` **in one commit** with the doctor's expected-cron
   list, the installer and the bridge generator — a stale expected-list is a doctor FAIL.

**Exit:** `grep -rl cortex ~/.config/systemd/user/` == 0 (except deliberate keeps); every cron
fires green; doctor 0 fail.

### P6 — Skills and gate rewiring (strict order)
1. Author the new `fleet-*` skill dirs + `name:` frontmatter; commit **under the old gate names**.
2. Deploy; `skill_view` each new name in a session, so the gate can see it loaded.
3. Rewire every gate literal: enforcer `_PATH_CTX_HINTS` / `_EXT_DOMAIN_SKILLS` /
   `_FILENAME_DOMAIN_SKILLS` / both block messages, the pre-commit ritual loop,
   `reflexion-check.py` `DEFAULT_SKILL`, `skills.yaml`, `docs/SKILLS-MANIFEST.md`,
   `docs/guardrail-registry.json` `restraint:` targets.
4. Delete the old dirs in a later commit.

**Exit:** a production-code write, a test-file write and a deploy-path write are each permitted
after loading only the new names; the doctor's restraint check passes; no `skill:<old>` target
remains in the guardrail registry.

### P7 — Land it fleet-wide (0 residuals is NOT done)
1. **Automatic per-host migration** on the update path: `migrate-cortex-to-fleet.sh`, idempotent,
   seeded from the old state, run by the deploy before anything reads the moved thing — so a host
   left on the old layout self-heals on its next update.
2. **A doctor FAIL check** on the new invariant (target exists, old path absent or a symlink to
   it) with a `fix:` line naming the exact script.
3. **A runbook** `docs/runbooks/cortex-to-fleet-rename.md` — Linux *and* macOS sections, a
   symptom → cause → fix table, the deliberate-keeps list; indexed in `docs/DOCS-INDEX.md`.
4. **Agent-facing skill notes** updated (the setup/troubleshooting skills agents actually load).
5. **Fleet dispatch** — `UPDATE_REQUEST` on the bus, per-agent `FLEET_NOTICE`, delivery verified in
   the DB (never trust a "created" response).

**Exit:** every host reports converged (doctor 0 fail, `grep -rl cortex` clean on live surfaces);
the migration is proven idempotent by running it twice.

---

## 6. Strategy — staged + names-only (operator decision Q3), not big-bang

**Stage it.** Three of the §4 contracts — the sanctioned deploy regex, 138 env vars living in
host files, hand-installed systemd units — fail *silently* and *per host*. A single-commit sweep
cannot be verified on one host and shipped; it has to be correct on four-plus hosts simultaneously
with no intermediate observable state. Staging buys one observable checkpoint per contract, and
the compat shims make rollback a `git revert` rather than a per-host rewrite. The 2026-11-04
revert was caused by a bang, not by the boundary — the stages are the corrective.

**Names-only is the decided scope (Q3), not an option.** `CORTEX_*` env vars are **deferred** to a
follow-on release: this sweep renames every `cortex-` / `cortex_` / `Cortex` / `\bcortex\b`
*identifier and filename* — ≈ **6,735** (9,845 sweep-scope − 3,110 `CORTEX_` family) — but leaves
the `CORTEX_*` variable NAMES untouched. §5 P4 remains in the plan purely as the *spec* for that
later env-var change; it is **not** part of the current execution. The existing `CORTEX_*` reads
stay live across all hosts; a later release adds the `FLEET_*` dual-read then drops the old names.

> **Scope guard for P0–P7:** the sweep's replacement table and residue greps cover the four
> non-env families. `CORTEX_*` is in the §4.2 risk register and §5 P4 only — never in any
> phase's replacement pass. A residue grep that would touch `CORTEX_` is scoped out of every
> phase below.

**Rejected — one big-bang sweep** (the 2026-11-04 pattern). That worked for `hermes-cortex` because
the swept token was mostly paths under one home directory, with a transition symlink to absorb
misses. Here there is no symlink to absorb a missed unit name; the failure mode is a silently wrong
default, and it is exactly what got reverted.

---

## 7. Verification battery (every phase)

- `bash -n` every changed `.sh`; `py_compile` every changed `.py`; YAML `safe_load`; JSON `load`.
- Adversarial static gate: `adversarial-verify.py --file <f> --level A2 --gate`; **A4** for
  `plugins/`, `hooks/`, `mcp-servers/`, `ops/scripts/manage/`, `fleet_doctor/`, the enforcer,
  `tests/`. Never `--no-verify`.
- Residue grep per spelling of the ACTIVE families, **each spelling independently** (`cortex-`,
  `cortex_`, `Cortex`, `\bcortex\b`) — plus the mangle greps (space-inside-token, title-case
  command garbles) and — for any *path* or *file* rename — the **construction** grep (e.g.
  `"core" */ *"fleet_bus"`), because a flawless token sweep leaves segment-built paths pointing at
  a file that no longer exists.
  `CORTEX_` residue is **deliberately NOT in this list** for P0–P7 (it is the deferred env-var
  family, §6 scope guard) — it becomes part of the battery only when §5 P4 is executed.
- `git grep -c mycortex` **unchanged per file**, and `git grep -c hermes-cortex` unchanged except
  the deliberately-repointed artifacts (dashboard unit, `hermes-cortex.env.example`, host
  transition tooling) — the §3.2/§3.3 assertions.
- Sibling tests at the changed seams: `test_repo_resource_paths.py`,
  `test_gateway_modules_are_deployed.py`, `test_registered_sources_are_tracked.py`,
  `test_cortex_doctor_*`, `test_skills_loadable_check.py`.
- Dogfood: the **deployed** copy runs its real invocation, not the repo copy.
- `cortex-doctor.py --quiet` → record the **exit code and warning count**, not just the ✅ lines.
- Deploy, **then** push, nothing committed in between; `verify-landed.py --repo . --base <prev tip>`.
- Evidence committed to `docs/evidence/` in the same cycle — a load-bearing claim living only in a
  close note is filed unverified-claim.

---

## 8. Rollback

- **P1, P6** — `git revert`; no runtime state.
- **P2, P3** — the compat shims mean both names resolve, so a revert is safe in either direction.
- **P4** — the dual-read fallback means a reverted host keeps working on `CORTEX_*`. This is the
  only phase where a rollback must not precede a host config repoint.
- **P5** — old unit files stay on disk (disabled, not deleted) for one release; re-enable to roll back.
- Inherited hard rule: **never run the per-host migration under an in-flight deploy** writing to the
  same directories.

---

## 9. Governance-critical couplings — the "do not break this" list

1. `plugins/governance-enforcer/__init__.py:2013,2018` — the sanctioned `cortex-update.sh`
   invocation (fleet-wide deploy lockout if missed). **Dual-accept first, rename second.**
2. `ops/scripts/cortex-update.sh` `register()` map — **388** map entries (346 `register` + 42
   `register_orch`; 445 `register` token occurrences in comments/code; **383** entries with a
   `${CORTEX_DEPLOY_HOME}/` deployed shape — the number the doc test parses — and **5** `${HOME}/`
   shapes: four langfuse files + the macOS dashboard plist). **Reconciled and recorded in P0**
   (2026-11-06): the previous figures were stale — the doc/test pair was failing at HEAD
   (doc said 386, map is 388/383) and is now fixed and green. Use 388 as the sweep base; the
   deployed path is **not derivable** from the repo path (131 of the 383 follow the strip-`ops/`
   rule; 252 do not). Use `cortex_lib.paths.resolve_repo_resource`; verify on the deployed tree.
3. `ops/scripts/cortex-dogfood.sh:23` + `pre-push-pull` — the pre-push gate chain.
4. `cortex_lib/paths.py` parent-walk bootstrap — byte-identical in every MCP server.
5. `~/.hermes/config.yaml` `mcp_servers.*.args` — security-sensitive; `hermes config set` only.
6. The `.git/hooks` symlink set + `core.hooksPath` — installed from the repo, immutable; needs the
   orchestrator unlock to repoint.

---

## 10. Open questions — RESOLVED (operator, 2026-11-06)

All four are closed by the operator and recorded in the §*decisions* table at the top; they are
listed here so the resolution is adjacent to where the questions were first asked.

- **Q1 — resolved: staged, not a bang.** The 2026-11-04 attempt was reverted because it was too
  big a single change. The boundary holds; §5's stages are the corrective. No boundary change.
- **Q2 — resolved: dashboard joins.** `hermes-cortex-dashboard.service` →
  `fleet-dashboard.service`; the plist follows. Supersedes the earlier "keeps its name" note.
- **Q3 — resolved: names-only.** `CORTEX_*` env vars deferred to a follow-on release. This sweep
  is ≈ 6,735 sweep-scope (the four non-env families); §5 P4 is spec-only for the later change.
- **Q4 — resolved: leave for a third sweep.** The four `hermes-cortex*` skills keep their
  `name:` load key; this plan does not rewire their gates.

---

## 11. Alternatives considered

| Option | Why rejected |
|---|---|
| Big-bang single sweep | No symlink absorbs a missed unit name; failures are silent and per-host — and it is what actually got reverted on 2026-11-04 (§6) |
| Names-only, keep `CORTEX_*` | Now the operator DECISION, not a rejection — Q3 defers the env vars, which stay live until a follow-on release (all other options below are against the resulting scope) |
| Include env vars now | The most expensive and least valuable part (139 host-backed names); deferred by Q3 to keep this sweep shippable in stages — §5 P4 is its spec |
| Leave `cortex` as-is | It is the last framework brand straggler; the 2026-11-04 rename explicitly deferred it as "a SECOND, larger sweep with its own runtime-contract risks". This is that sweep |
| Rename the DB / role to match | `mycortex` is a different product with live data; out of scope (§3.2) |

---

## 12. Deliberately NOT proposed

- **No `sed -i` fleet pass.** The ordered guard table (§3) is built and dry-run first; the sweep
  asserts its match count before writing, then is scanned for artefacts (escaping residue,
  duplicates, self-contradicting never-clauses).
- **No rebase.** Sibling pushes integrate with `git merge` — the review receipt is tied to the
  range's commits.
- **No `--no-verify`, no `SKIP_SCORE=1`, no `force=true`.** Every phase is a scored cycle.
