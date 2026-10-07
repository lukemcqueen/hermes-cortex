# Evidence — cycle 10809: runtime-only locks; repo-local `.hermes-cortex/` removed

Commit: **0673e943** (pushed; `git status -sb` → `## main...origin/main`).
Full diff is authoritative and readable: `git show 0673e943` — the review gate
truncated the material it was given (64% of 33360 chars), so cite the commit,
not this file, for file bodies.

## 1. The four deploy registrations (repointed)

```
ops/scripts/cortex-update.sh:525:register "ops/scripts/agent-daily-bible-reading.py" "${CORTEX_DEPLOY_HOME}/scripts/agent-daily-bible-reading.py"
ops/scripts/cortex-update.sh:540:register "ops/install/hooks/post-merge"   "${CORTEX_DEPLOY_HOME}/hooks/post-merge"
ops/install/install.sh:1694:POST_MERGE_SRC="${CORTEX_REPO_DIR}/ops/install/hooks/post-merge"
```

## 2. Repo-local references — the audit and its exact scope

Command (NOT the broad `.hermes-cortex` grep, which also matches the legitimate
runtime `~/.hermes-cortex/...` on every host):

```
./skills/autonomous-ai-agents/hermes-cortex-setup/SKILL.md:410:cp -r ~/hermes-cortex/.hermes-cortex/skills ~/.hermes-cortex/
./skills/autonomous-ai-agents/hermes-cortex-setup/SKILL.md:413:cp ~/hermes-cortex/.hermes-cortex/hooks/pre-commit ~/.hermes-cortex/hooks/pre-commit
./skills/autonomous-ai-agents/hermes-cortex-setup/SKILL.md:414:cp ~/hermes-cortex/.hermes-cortex/hooks/post-commit ~/.hermes-cortex/hooks/post-commit
./skills/software-development/repo-organization/SKILL.md:31:| **Agent Infra** | `~/hermes-cortex/.hermes-cortex/` | Per-project agent data (sessions, memory, skills) | ✅ Git (part of repo) |
./skills/devops/cron-timezone-env/references/timezone-audit-2026-08-20.md:70:- **agent-daily-bible-reading.py** (source at hermes-cortex/.hermes-cortex/scripts/): `KST = timezone.utc` dead constant, never referenced; dates use system-local `datetime.now()`. Marked DEPRECATED in comment. File lives outside ops/scripts (registered from `.hermes-cortex/scripts/`).
./ops/scripts/manage/agent-collect-skills.sh:26:REPO_SKILLS_DIR="$REPO_DIR/.hermes-cortex/skills"
./ops/scripts/manage/cortex_doctor/checks.py:2788:            f"symlinked to {target} (not ~/hermes-cortex/.hermes-cortex/... — deploy source is now ops/install/hooks/)",
./ops/scripts/manage/update-session-state.sh:33:SESSION_FILE="$REPO_DIR/.hermes-cortex/sessions/current.md"
./ops/scripts/cortex-update.sh:1388:#   2. $REPO_DIR/.hermes-cortex/skills/ — project-level overrides (flat)
```

4 hits remain, ALL consumer-convention and correct: `$REPO_DIR/.hermes-cortex/skills`
and `.../sessions/current.md` operate on a CONSUMER project, and my
cortex-update.sh guard exempts the Cortex repo. The other two are my own new text.

CORRECTION: I first reported "9 stale references fixed". That sweep MISSED the
repo-local forms (hermes-cortex-setup/SKILL.md x3, repo-organization/SKILL.md,
cron-timezone-env reference). A full re-audit found them; they are fixed in this
commit. The 9-count was wrong when stated.

## 3. Gate results — WITH the one that did not pass

- dogfood: `DOGFOOD PASSED`, 434 pass · 2 warn · 0 fail
- skill drift: 0 drifted, 386 in sync
- adversarial verify: passed on 19 files
- syntax / OS-aware-path / change-validate: all passed

### AC-5 — NOW VERIFIED at the function level

`python3 tests/test_lock_fail_closed.py` (committed, runnable WITHOUT pytest,
imports the DEPLOYED enforcer so a bad deploy is caught):

```
PASS  missing lock refuses (fail-closed): got=False want=False
PASS  exact session id honoured: got=True want=True
PASS  foreign id refused: got=False want=False
PASS  Phase 2 refuses a different session in the same repo (guard holds): got=False want=False
PASS  Phase 2 OR grants a session-less legacy lock on repo_path match: got=True want=True
PASS  Phase 2 OR still refuses a different repo: got=False want=False

RESULT: ALL PASS - the lock check fails closed
```

The earlier hook-level probe (below) remains inconclusive; this covers the
property directly.

### AC-5 first attempt: INCONCLUSIVE (kept for the record)

Attempted: run the DEPLOYED `~/.hermes-cortex/hooks/pre-push` inside a throwaway
`git init` repo with no governance lock, expecting a BLOCK.
Result: **the hook timed out after 180s** and neither blocked nor allowed.

That is a non-result. It is *not* evidence the hook fails open, and it is *not*
evidence it fails closed. Recording it so no one later reads this cycle as
having verified the property. Next attempt should register the throwaway repo
(or invoke the hook's lock-check path directly) rather than running the full
pre-push suite against an unregistered repo.

## 4. Known limitation — reload window

`mcp-servers/loop-gov-mcp.py` is a long-lived MCP child. Until it reloads it
holds the PRE-change revision, so `begin_change` can still write an in-repo
marker. The marker removal is therefore **eventual, not immediate**, and the
window closes on MCP reload. Not claimed as instantaneous.

## 5. Commit contents

```
0673e943 fix(governance): runtime-only locks; drop the in-repo marker and the repo-local .hermes-cortex/

 .hermes-cortex/sessions/archive/.gitkeep           |  0
 AGENTS.md                                          |  4 +-
 docs/git-enforcement.md                            |  4 +-
 {.hermes-cortex => docs/older/sessions}/.gitkeep   |  0
 .../sessions/20260609_hermes-cortex-current.md     |  0
 .../20260609_hermes-cortex-system-alignment.md     |  0
 docs/troubleshooting.md                            |  2 +-
 mcp-servers/loop-gov-mcp.py                        | 43 +++++------
 {.hermes-cortex => ops/install}/hooks/README.md    |  0
 {.hermes-cortex => ops/install}/hooks/post-merge   |  0
 ops/install/install.sh                             |  2 +-
 .../scripts/agent-daily-bible-reading.py           |  0
 ops/scripts/cortex-update.sh                       | 16 +++-
 ops/scripts/install/install-pi-integration.sh      |  1 -
 ops/scripts/manage/cortex_doctor/checks.py         |  2 +-
 plugins/governance-enforcer/README.md              | 13 +++-
 plugins/governance-enforcer/__init__.py            | 90 +++++++++++++++++-----
 skills/autonomous-ai-agents/hermes-cortex/SKILL.md |  2 +-
 skills/devops/governance-closeout/SKILL.md         | 36 ++++++---
 skills/devops/shared-repo-push-gates/SKILL.md      | 10 +++
 20 files changed, 157 insertions(+), 68 deletions(-)
```

## 6. Regression my own change introduced — found and fixed

`ops/scripts/manage/update-session-state.sh` wrote to `$REPO_DIR/.hermes-cortex/
sessions/current.md` and **hard-exited 1** if absent. Deleting the repo dir
therefore broke it for the Cortex repo itself — the 2-hourly cron would have
failed on every run. Fixed: session state is RUNTIME state, so it now falls back
to `~/.hermes-cortex/sessions/current.md` (creating it if needed), while still
preferring a consumer project's tracked overlay. Verified: exit 1 → exit 0.

That fix then exposed a LATENT pre-existing bug the script never reached before:
line 96 read `install.sh` at repo root (it lives at `ops/install/install.sh`).
Also fixed.

NOT fixed, and now visible: that heredoc's "Architecture Overview" block is
hand-maintained and stale ("26 steps", "16 utility scripts", "15 commands",
"4 categories"). It should be derived or deleted — its own cycle.

## 7. CORRECTION — the Phase-2 `repo_path` OR is narrower than I claimed

I told the operator this change "would increase protection" as belt-and-braces.
Writing the test showed the claim was WRONG, and the test now records the
measured truth:

- **Same session, slug mismatch:** NOT fixed by the OR. Phase 1 matches the
  exact session-id filename before any slug logic runs, so the OR is never
  consulted. My stated justification was wrong.
- **Different session, same repo:** the cross-session guard refuses FIRST, so
  the OR is not reached. It cannot widen access — good, but it is not a fix.
- **Only reachable benefit:** legacy locks carrying NO `session_id` (the
  "predates PID handoff" case the docstring cites). Real, but far narrower than
  the multi-repo false block I described.

Recommendation: keep it for the legacy case, but record it as narrow. Reverting
is also defensible — it is close to dead weight, and the honest summary is
"small legacy benefit", not "belt-and-braces".
