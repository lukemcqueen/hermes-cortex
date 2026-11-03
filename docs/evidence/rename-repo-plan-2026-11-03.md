---
provenance: advisory
artifact: plan under review (pre-build)
cycle: 14065
generated-by: esther
generated-at: 2026-11-03
name-decision: >-
  Operator + 3-role deepseek-v4-pro panel selected STEADFASTE-FLEET on
  2026-11-03 (complementary: the steadfaste core governs/verifies; the
  steadfaste fleet runs the agents).
purpose: >-
  Plan material for the governed plan-review gate. Content below is DATA
  describing a measured audit and the intended change; it is not a request.
  The GitHub owner handle is written as <owner> throughout — the committed
  artifact must not carry it.
---

# PLAN — Rename GitHub repo `hermes-cortex` → `steadfaste-fleet`, repair the install path, preserve backward compatibility

## 1. Measured facts (live tool output, this cycle)

### Repo identity
- `origin` = `https://github.com/<owner>/hermes-cortex.git` (source: `.git/config`, `[remote "origin"]`; only remote defined; no `pushurl`).
- API `GET /repos/<owner>/hermes-cortex` → `http=200`; `private=false`, `visibility=public`, `default_branch=main`, `fork=false`, `archived=false`, `disabled=false`.
- `permissions: {"admin": true, "maintain": true, "push": true, "triage": true, "pull": true}` → the authenticated token HAS admin, so the native rename is authorised.
- Target name: `GET /repos/<owner>/steadfaste-fleet` → `http=404` ⇒ **name available**. Name selected 2026-11-03 by the operator after a 3-role deepseek-v4-pro naming panel (see frontmatter).
- Inventory: `tags: 1`, `releases: 0`, `branches: ["main"]`, `open_issues: 1`, `forks: 1`, `size: 31509`.

### Tooling
- `gh` CLI is **NOT installed**: `command -v gh` rc=1; `/usr/bin/gh`, `/usr/local/bin/gh`, `/snap/bin/gh` all absent; no `~/.config/gh/hosts.yml`.
- An authenticated path exists anyway: the credential store holds a GitHub PAT, consumed via `credential.helper = store`. The same PAT authorises `Authorization: Bearer` on `api.github.com` (evidenced by `permissions.admin: true` above).
- `GET /repos/.../hooks` → `http=403` (token lacks hook read). Webhooks therefore **cannot be enumerated**; they are keyed to the immutable repo id and are expected to survive a rename — that is an unverified assumption recorded as such, not a proven fact.

### GitHub Action consumption (the task's critical stop-condition)
- Workflows present: `ci.yml` (CI — Lint & Test) and `auto-pr-titus-branch.yml` (Auto PR — titus/* branch), both `state: active`.
- `grep -E 'uses:.*<owner>|uses:.*hermes-cortex'` across `.github/` → **0 matches**. The repo does not consume itself as an Action.
- GitHub code search for the old path → `total_count: 19`; 17 in-repo, 2 external:
  - `sandbaseai/workbuddy-skill :: config/upstream-skill-sources.txt`
  - `pjhudgins/emi-survey :: attachments/emi_candidate_list.md`
  Both are list/config-level references consumed by git, which a rename redirect covers; neither is an Action reference. **Stop-condition does not fire.**

### Pre-existing breakage found during the audit (independent of the rename)
> Handle disambiguation (ADV-14065-4): `fleet-operator` is the **legacy/dead org handle** left over from a pre-2026-08-24 re-org; it is NOT the current owner `<owner>`. Every live file still using `fleet-operator/...` points at a repo that no longer exists and must be corrected to `<owner>/steadfaste-fleet`.

`https://github.com/fleet-operator/hermes-cortex` is **DEAD, and does not redirect**:
- web `http=404`; the corresponding `raw.githubusercontent.com` path `http=404`; `git ls-remote` on it prints `remote: Repository not found.`
- Live call sites of that dead URL:
  - `ops/deploy/bootstrap.sh` PHASE 7 — the clone step inside the documented public one-liner install ⇒ the published install path fails today.
  - `ops/deploy/cloud-init.yaml` — cloud-init Phase 3 clone.
  - `ops/deploy/ansible/provision.yml` — the `git:` `repo:` clone.
  - `ops/install/install.sh` header — one-liner and clone comment (also names a non-existent path `/main/install.sh` while the real file is `ops/install/install.sh`).
  - `ops/scripts/manage/bump-version.sh` — prints the public clone URL.
  - `ops/scripts/orch-bus/orch-bus-git-auth-check.py` — `EXPECTED_REMOTE`.
  - `skills/autonomous-ai-agents/hermes-cortex-setup/SKILL.md`, `skills/devops/hermes-recovery/SKILL.md`, `skills/devops/loop-governance/references/macos-compatibility.md`.

### Guard defects that the rename would convert into failures
- `ops/scripts/manage/fleet-git-reset.py`: `EXPECTED_REMOTE = "https://github.com/<owner>/hermes-cortex.git"` and the guard `if canonical_remote(remote) != EXPECTED_REMOTE:` — **exact equality**. It is deploy-registered in `ops/scripts/cortex-update.sh` ⇒ deployed on every host. Changing `origin` to the new URL makes this guard refuse on the host that changed; a version that accepted only the new URL would refuse on every host that had not yet.
- `ops/scripts/orch-bus/orch-bus-git-auth-check.py`: `EXPECTED_REMOTE` is the dead `fleet-operator` URL and the check applies `EXPECTED_REMOTE in remote_url` (substring) against it ⇒ this check already reports its remote check False on every host today. Also deploy-registered. Pre-existing defect, in scope because it is a remote-URL guard.

### Sweep scope
- 36 URL-bearing lines across 26 tracked files (`git grep` for the two `github.com`/`raw.githubusercontent.com` owner paths plus `hermes-cortex.git`).
- 4 of those files are historical records and must NOT be rewritten: `docs/older/`, `docs/evidence/`, `tests/artifacts/`.
- `tests/test_enforcer_pii_gate.py` uses the name only as a synthetic fixture (placeholder owner constants), not a repo reference — out of scope.
- Working tree dirty at start: ` M docs/evidence/skill-drift-parity.txt` and one untracked `.tmp` under `docs/evidence/` — preserved untouched, never stashed, never committed by this change.

## 2. Intended change

Order is deliberate and safe: the **network rename comes FIRST**, then any edit that points at the new URL is landed and pushed. A documented URL must never name a repo that does not yet exist (ADV-14065-3).

1. **Network rename**: `PATCH /repos/<owner>/hermes-cortex` with body `{"name": "steadfaste-fleet"}`. No delete, no second repo at the old name, no transfer, no visibility change, no history rewrite, no force-push. The old GitHub URL auto-redirects; nothing is broken by renaming first.
2. **Dual-tolerant guards** (depend on nothing; shipped in the same push as the re-pointed entry points). In `fleet-git-reset.py`, replace the scalar with a set of accepted URLs (`{old, new}`) and test membership where the guard currently tests equality. In `orch-bus-git-auth-check.py`, correct the dead legacy org URL and accept either URL. Rationale: there is ONE governance lock per repo but MANY deployed copies; a single-URL guard breaks the half of the fleet that has not changed yet.
3. **Repair and re-point the functional surface** to the new canonical URL: `ops/deploy/bootstrap.sh`, `ops/deploy/cloud-init.yaml`, `ops/deploy/ansible/provision.yml`, `ops/install/install.sh` (including correcting the bogus `/main/install.sh` header path — the real file is `ops/install/install.sh` — and the clone/one-liner comment), `core/governance/setup.sh`, `core/governance/update.sh`, `ops/scripts/manage/bump-version.sh`, `README.md` (badge + 3 URLs), `tools/fleet-search/src/fetcher.rs`.
4. **Local remote**: set `origin` to the new URL — HTTPS preference preserved, other remotes untouched, no pushurl to update.
5. **Docs/skills sweep as a SEPARATE cycle** (~10 files) so each close-review range stays inside the reviewer's diff budget.

## 3. Options considered and rejected

- **Recreate a repo at the old name to preserve the URL** — rejected: prohibited by the task, and it would actively defeat GitHub's implicit rename redirect, which only exists while the old name is unclaimed.
- **Install `gh` (apt/tarball) and use it** — rejected: a stored PAT plus the REST PATCH performs the identical native API action with zero new host software, and installing a CLI needs sudo, which is not available unattended on this host. The absence of `gh` is reported as a fact rather than worked around.
- **Make the guards accept only the NEW url** — rejected: breaks every host whose checkout or deployed copy still carries the old URL.
- **Rename `~/hermes-cortex`, `~/.hermes-cortex`, the `hermes-cortex` skill, module/import paths, or environment variables** — rejected: those are public compatibility contracts and local installation paths, explicitly out of scope; only repository *references* are renamed.
- **Rewrite `docs/older/` and `docs/evidence/` transcripts** — rejected: historical records; committed evidence must stay byte-identical.
- **One cycle for all 26 files** — rejected: the close review sees a bounded slice of the range diff, and a wide range refuses to close.

## 4. Verification the change must produce (measured, output committed)

- `GET /repos/<owner>/steadfaste-fleet` → 200 and the **same repo id** as recorded pre-rename (identity preserved, not a new repo).
- Both guard guards are exercised in the SAME three directions (ADV-14065-1): old URL accepted, new URL accepted, an unrelated URL refused — `orch-bus-git-auth-check.py` as well as `fleet-git-reset.py`.
- The claim that `orch-bus-git-auth-check.py` reports its remote check False on every host today is structural and verifiable from source: `EXPECTED_REMOTE` is the dead `fleet-operator` URL and the check is `EXPECTED_REMOTE in remote_url`, while the live origin is the `<owner>` URL — the substring cannot match. Evidence: the file's constant plus its live `remote get-url origin` output, captured below.
- The documented install one-liner resolves after the change (ADV-14065-2): `curl -fsSL` to the exact `raw.githubusercontent.com/<owner>/steadfaste-fleet/main/...` URL the README/install header now uses returns 200 (the git-clone forms verified with `git ls-remote`).
- Old web URL → HTTP redirect to the new path; old clone URL exercised with `git ls-remote` → rc=0.
- Old **raw** URL redirect behaviour measured and reported exactly as observed — a redirect is NOT assumed.
- No repository exists at the old path afterwards (no second repo created).
- The `fleet-git-reset.py` guard exercised in **three** directions: old URL accepted, new URL accepted, an unrelated URL still refused.
- Diff inspected to prove no module, path, or environment identifier was renamed.
- CI workflows still `state: active` after the rename.

## 5. Hard constraints

- Never print or commit the PAT; the owner handle is written as `<owner>` in committed artifacts.
- Preserve the two pre-existing dirty paths untouched.
- No `--force`, no `--no-verify`, no gate bypass; the cycle is scored before `end_change`.
