# Plan — `cortex-` short-name rename (`cortex-*` / `cortex_*` / `CORTEX_*` → `fleet-*`)

> **Status:** PLAN — not started. Awaiting operator decision on §3 (boundary) and §6 (staged vs big-bang).
> **Author:** Esther (orchestrator). **Governance cycle:** #14235.
> **Predecessors:** the `hermes-cortex` → `steadfaste-fleet` sweep (2026-11-04, 938 files) and the
> `hc-` prefix drop (`aa03092f`, 2026-11-06). Both left the **`cortex` short-name family** in place
> on purpose — see `docs/rename-followups-steadfaste-fleet.md`, §*"The `cortex` short-name family is
> a SEPARATE naming layer (not covered)"*. This document is that second sweep.

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

Computed 2026-11-06 over `git ls-files` (3,511 tracked files), compiled caches skipped.

> **Evidence (committed in this cycle, re-runnable):**
> `docs/evidence/cortex-to-fleet-scope-2026-11-06.py` + `.txt` — emits §2, §4.2 and §9.2 verbatim.
> `docs/evidence/cortex-to-fleet-worktree-2026-11-06.sh` + `.txt` — emits §4.7 and §4.8 verbatim.
> Both are READ-ONLY and are run from the repo root; every number below comes from those runs.
> Each `.txt` is the captured stdout of its sibling script, recorded at `HEAD = 36670678` with
> `origin/main` at the same sha.

| token family | total hits | files | **in-scope** hits |
|---|---:|---:|---:|
| `cortex-` (hyphen) | 6,449 | 1,017 | 3,898 |
| `cortex_` (underscore) | 2,552 | 579 | 2,070 |
| `CORTEX_` (env / const) | 3,366 | 489 | 3,141 |
| `Cortex` (title case) | 413 | 172 | 276 |
| `\bcortex\b` (bare word) | 4,025 | 659 | 908 |
| **in-scope total** | | | **≈ 10,293** |

Tracked paths whose name contains `cortex` (excluding `mycortex`): **192**, of which **32** are
records → **160 live paths** to rename.

Bare-`cortex` is concentrated in record directories; the in-scope bare-word count is only 908.

### 2.1 Densest in-scope carriers (measured)

```
 817  ops/scripts/cortex-update.sh                 (register() map — governance-critical)
 379  ops/scripts/manage/cortex_doctor/checks.py
 227  ops/install/install.sh
 173  skills/autonomous-ai-agents/hermes-cortex/SKILL.md
  94  tests/test_skills_ownership.py
```

`ops/scripts/cortex-update.sh` holds **346** `register "<repo>" "<deployed>"` map entries — the
single densest file and the governance-critical one (§4.1). See §9.2 for the count reconciliation.


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
| Config / unit templates | `ops/install/deploy/config/cortex-config.yaml`, `ops/install/deploy/cortex-bus.service`, `hermes-cortex.env.example`, `docs/templates/cortex-gateway.service`, `docs/templates/com.hermes.cortex-gateway.plist`, `com.hermes.cortex-dashboard.plist`, `ops/services/dashboard/com.hermes.cortex-dashboard.plist` | `fleet-*` |
| Pi-harness extensions | `cortex-context.ts`, `cortex-governance.ts` | `fleet-context.ts`, `fleet-governance.ts` |
| Env vars | `CORTEX_*` — **~150 distinct names**, 3,366 hits | `FLEET_*` |
| systemd units | `cortex-bridge-*` (~90 service + timer + `.wants`), `cortex-bus.service`, `cortex-gateway.service`, `cortex-gateway-<agent>.service` | `fleet-bridge-*`, `fleet-bus`, `fleet-gateway` |
| Cron names (`~/.hermes/cron/jobs.json`) | `cortex-bus-workday`, `cortex-bus-evening`, `cortex-bus-overnight` | `fleet-bus-workday`, `fleet-bus-evening`, `fleet-bus-overnight` |
| Skill load keys | `cortex-bus`, `cortex-bus-automation`, `cortex-bus-inbox`, `cortex-bus-messaging`, `cortex-bus-polling`, `cortex-preflight`, `cortex-deployment-sync` | `fleet-bus*`, `fleet-preflight`, `fleet-deployment-sync` |
| Live docs | `docs/design/cortex-gateway.md`, `cortex-gateway-parity.md`, `cortex-memory-session-mcp.md`; `docs/runbooks/cortex-env-migration.md` | `fleet-*` |
| Prose | `Cortex` / `cortex` where it names the framework | `Fleet` / `fleet` |

### 3.2 KEEP — `mycortex` is a different product

`mycortex` is the knowledge brain; its `cortex` is a substring of a **different word**. Never
match it, never "fix" it, never rename its `cortex` half:

- PG: database `mycortex`, roles `mycortex` / `mycortex_admin`, schema `mycortex.*`
  (`ops/services/mycortex/schema/mycortex.sql`). `CORTEX_BUS_PG_DB` **defaults to** the value
  `mycortex` (`core/cortex_bus/queue.py:28`) — the **variable name** renames, its **value** does not.
- `plugins/mycortex-mem/`, `plugins/mycortex-command/`, `ops/services/mycortex-mem/`,
  `ops/services/mycortex/`, `ops/install/deploy/docker-compose.mycortex.yml`
- `mycortex` CLI, `mycortex-parity.py`, `agent-mycortex-sync.sh`, `agent-mycortex-retention.py`
- `agent-mycortex-dream-*` crons; `skills/devops/mycortex/`; `docs/design/mycortex-*.md`

> **Guard rule (first guard in the ordered pass, before any case-preserving catch-all):** every
> replacement regex on `cortex` carries a negative lookbehind for `my`, i.e. `(?<!my)cortex`.
> **Post-condition:** `git grep -c mycortex` is **unchanged per file** (same count before and
> after) — this is the assertion that proves §3.2 held.

### 3.3 KEEP — already decided 2026-11-04 (unless §10 Q2/Q4 overturn it)

- Skill dirs + `name:` frontmatter for `hermes-cortex`, `hermes-cortex-setup`,
  `hermes-cortex-maintenance`, `hermes-cortex-repo-deploy` — the `skill_view(name=...)` load key.
- The enforcer's dual-URL accept list `(hermes-cortex|steadfaste-fleet)`.
- `hermes-cortex-dashboard.service` — **flagged**: this plan's §3.1 table would sweep it, which
  contradicts the follow-ups doc. Operator call needed (§10 Q2).

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
- Detection/report messages whose *subject* is the old name (doctor "stray …", enforcer brand
  allow-list entry) — the old name is the SUBJECT of the sentence, not a path to resolve.
- `docs/rename-followups-steadfaste-fleet.md`, `docs/runbooks/fleet-local-dir-rename.md` and
  **this plan** — a path-token replace rewrites both sides of their `old → new` mapping lines,
  inverting them to `new → new` and silently deleting the worked example. (Measured pitfall:
  `rename-sweep`'s own worked example was corrupted exactly this way.)
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

**139** distinct `CORTEX_*` names, **3,356** occurrences. The **values** live in files a repo sweep
cannot touch: `~/.steadfaste-fleet/.env`, `~/.steadfaste-fleet/agent.env`, systemd `Environment=` /
`EnvironmentFile=`, nginx site configs (`CORTEX_NGINX_PORT_PREFIX`, `CORTEX_DOMAIN`), the Pi-harness
manifests, and every peer host's own `.env`. Top carriers (measured):

```
717 CORTEX_DEPLOY_HOME      479 CORTEX_REPO          250 CORTEX_HOME
193 CORTEX_BUS_URL          132 CORTEX_SESSION_REPO  126 CORTEX_BUS_TOKEN
 97 CORTEX_BASIC_AUTH        88 CORTEX_BUS_FALLBACK_URL
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
ever a host artifact, never a committed source. **Open question §10 Q1: what reverted the Nov-4
attempt, and does its reason still apply?**

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
3. Answer §10 Q1 — read the Nov-4 revert history with Moses.
4. Write `docs/rename-cortex-to-fleet.md` (the §3 boundary + the ordered guard table, in the
   `rename-followups` pattern) and index it in `docs/DOCS-INDEX.md`.
5. Freeze: no concurrent rename in flight anywhere on the fleet; one owner.

**Exit:** index clean; residue count 0; boundary doc committed; Q1 answered.

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
   **forwarding shim** for one release; update all 353 `register()` deployed-path targets and every
   caller (`cortex-dogfood.sh:23`, `pre-push-pull`, `install-crons.sh`,
   `install-cortex-update-cron.sh`, the bridge generator, the doctor's expected lists).
3. Sweep the remaining script/module filenames from §3.1.

**Exit:** `bash -n` all; the deploy runs **from the new name** on a host (RC=0, doctor 0 fail);
the old name still works via the shim; `tests/test_repo_resource_paths.py` passes (it computes the
register-map numbers).

### P4 — Env vars `CORTEX_*` → `FLEET_*`, dual-read
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
   `cortex-gateway-<agent>`, and the dashboard unit per §10 Q2): `disable` old → `enable` new →
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

## 6. Strategy — staged (recommended) vs big-bang

**Recommended: the staged plan above.** Three of the §4 contracts — the sanctioned deploy regex,
~150 env vars living in host files, hand-installed systemd units — fail *silently* and *per host*.
A single-commit sweep cannot be verified on one host and shipped; it has to be correct on four-plus
hosts simultaneously with no intermediate observable state. Staging buys one observable checkpoint
per contract, and the compat shims make rollback a `git revert` rather than a per-host rewrite.

**Rejected — one big-bang sweep** (the 2026-11-04 pattern). That worked for `hermes-cortex` because
the swept token was mostly paths under one home directory, with a transition symlink to absorb
misses. Here there is no symlink to absorb a missed `CORTEX_*` read or a missed unit name; the
failure mode is a silently wrong default.

**Rejected — names only, keep `CORTEX_*`.** The env vars are 3,141 in-scope hits and the loudest
brand straggler, but also the most expensive and least valuable item (§4.2). If proportionality
wins, P4 becomes optional and the token set shrinks to ≈ 7,150. **This is §10 Q3.**

---

## 7. Verification battery (every phase)

- `bash -n` every changed `.sh`; `py_compile` every changed `.py`; YAML `safe_load`; JSON `load`.
- Adversarial static gate: `adversarial-verify.py --file <f> --level A2 --gate`; **A4** for
  `plugins/`, `hooks/`, `mcp-servers/`, `ops/scripts/manage/`, `fleet_doctor/`, the enforcer,
  `tests/`. Never `--no-verify`.
- Residue grep per spelling, **each spelling independently** (`cortex-`, `cortex_`, `CORTEX_`,
  `Cortex`, `\bcortex\b`), plus the mangle greps (space-inside-token, title-case command garbles)
  and — for any *path* or *file* rename — the **construction** grep (e.g.
  `"core" */ *"fleet_bus"`), because a flawless token sweep leaves segment-built paths pointing at
  a file that no longer exists.
- `git grep -c mycortex` **unchanged per file** — the §3.2 assertion.
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
2. `ops/scripts/cortex-update.sh` `register()` map — **346** `register "<repo>" "<deployed>"`
   entries (measured: `grep -cE '^[[:space:]]*register[[:space:]]+"'`, evidence §4). The deployed
   path is **not derivable** from the repo path — `docs/deploy-registry-pattern.md` states "255 of
   the 386 follow no rule", and that 386 is a *third* figure computed by
   `tests/test_repo_resource_paths.py`, which is the authority the doc says to keep in sync.
   **Reconcile the three numbers (346 anchored calls / 445 `register` tokens / 386 asserted by
   the test) in P0 before any `register()` line is edited** — a sweep driven by the wrong base
   count silently leaves entries un-renamed. Use `cortex_lib.paths.resolve_repo_resource`; verify
   on the deployed tree.
3. `ops/scripts/cortex-dogfood.sh:23` + `pre-push-pull` — the pre-push gate chain.
4. `cortex_lib/paths.py` parent-walk bootstrap — byte-identical in every MCP server.
5. `~/.hermes/config.yaml` `mcp_servers.*.args` — security-sensitive; `hermes config set` only.
6. The `.git/hooks` symlink set + `core.hooksPath` — installed from the repo, immutable; needs the
   orchestrator unlock to repoint.

---

## 10. Open questions — operator decisions needed

- **Q1.** What reverted the 2026-11-04 `cortex`→`fleet` attempt (§4.7)? If the reason still
  applies, the boundary changes. Needs the history from Moses before P0 closes.
- **Q2.** Does the dashboard unit join this rename, or stay `hermes-cortex-dashboard` per the
  2026-11-04 follow-ups? §3.1 and §3.3 currently contradict each other on this one artifact.
- **Q3.** Scope: full sweep (≈ 10,293 hits including `CORTEX_*`), or names-only (≈ 7,150, env vars
  deferred to their own release)? §6.
- **Q4.** Fold the four `hermes-cortex*` skills in now, or leave them to a third sweep? Their
  `name:` is a load key and a separate gate-rewiring job.

---

## 11. Alternatives considered

| Option | Why rejected |
|---|---|
| Big-bang single sweep | No symlink absorbs a missed `CORTEX_*` read or unit name; failures are silent and per-host (§6) |
| Names-only, keep `CORTEX_*` | Leaves 3,141 of ≈ 10,293 hits — kept as §10 Q3, not dismissed |
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
