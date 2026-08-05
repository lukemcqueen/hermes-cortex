---
name: enforcement-change-safety
version: 1.0.0
category: devops
description: "Use before enforcement code changes or shared-repo commits."
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [governance, enforcement, security, git, concurrency, hooks]
    related_skills: [enforcer-modification-considerations, change-checklist, two-hard-rules, loop-governance]
---

# Enforcement Change Safety

**Load BEFORE touching any enforcement/governance code: git hooks (pre-commit,
pre-push, post-commit), the enforcer plugin, the loop-governance MCP server, or
the scoring pipeline.** Also load when doing ANY git operation in a repo that
other agent sessions share.

This skill exists because a single misread of a "fix the warning" request
deleted the entire scoring subsystem (the heart of loop governance), and a
careless `git commit` swept another session's staged work into the wrong commit.
Both were trust-destroying, user-corrected mistakes (2026-08-03).

## Rule 1: NEVER Decrease Enforcement to Fix a Warning

When an issue says "remove the stale X block so the warning stops printing":

- **Remove the NOISE path, never the enforcement capability.**
- The stale part is usually a `warn + exit 0` when a dependency is missing —
  that `exit 0` SHORT-CIRCUITS the hook early, skipping every downstream guard
  (orchestrator-only paths, self-test, adversarial scan). THAT is the bug.
- Fix: convert the missing-dependency path to **FAIL CLOSED** — `exit 1` with a
  message pointing at the sanctioned fix (e.g. `cortex-update.sh`). A commit
  without a governance record must not land.
- Luke's hard rule (2026-08-03): "NEVER DECREASE SECURITY TO ENFORCER". "Instead
  of 'skipping', have the logic be FAIL IMMEDIATELY if the binary is gone."
- The MCP server is the PRIMARY enforcement layer; the hook is secondary. But
  "secondary" does NOT mean removable — the hook's scoring keeps the loop DB
  populated and its guards catch direct-git bypasses. Deleting it eliminates the
  entire function of the loops.

### Checklist when asked to remove a "stale block"
- [ ] Find the block's exact boundaries — what runs AFTER it that an early
      `exit 0` would skip?
- [ ] If the block warns + `exit 0` on missing dependency → the early exit IS
      the bypass; convert to `exit 1` (fail closed).
- [ ] Keep every enforcement capability intact: scoring pipeline (task-id slug,
      cycle auto-increment, code/prev file assembly, pass-rate, scorer
      invocation, DB write, hard-block on failure), path guards, self-test,
      adversarial scan.
- [ ] Diff must show ONLY the block changed — zero lines of enforcement removed.
- [ ] `bash -n` the hook; live-test BOTH branches (dependency present → scoring
      runs; dependency missing → exit 1).
- [ ] Deploy via the sanctioned path (`cortex-update.sh`), verify deployed copy
      byte-identical to repo source, verify fail-closed present in deployed.

## Rule 1b: macOS Portability of the Fail-Closed Hook

A hook that fails closed when a scorer binary is missing must actually FIND the
binary on macOS, or every commit on Titus blocks:

- **macOS has no `~/.local/bin` in PATH by default** — `command -v score-cycle`
  fails even when installed. Add the canonically-deployed path as a search
  candidate: `$HOME/.hermes-cortex/tools/loop-governance/score_cycle.py`
  (cortex-update.sh registers it there on BOTH Linux and macOS). Test the search
  with an emptied PATH to prove the deployed-path candidate resolves.
- **macOS has no `timeout` command** (coreutils provides `gtimeout`). Resolve
  the timeout binary portably before the scorer invocation:
  ```bash
  _TIMEOUT_BIN=""
  if command -v timeout >/dev/null 2>&1; then _TIMEOUT_BIN="timeout 30"
  elif command -v gtimeout >/dev/null 2>&1; then _TIMEOUT_BIN="gtimeout 30"
  fi
  SCORE_OUTPUT=$($_TIMEOUT_BIN "$PYTHON_BIN" "$SCORE_CYCLE" ...)
  ```
  Empty `_TIMEOUT_BIN` = unbounded run; the `||` hard-block still guards.
- macOS ships bash 3.2 — `for-in`, `command -v`, `[[ -z ]]`, `$()` are safe;
  `grep -P`, `mapfile`, `${var,,}` are NOT. Check the whole hook, not just your
  edit.
- The pre-existing hook ALREADY uses `<<<` herestrings and `[[ =~ ]]` — both are
  bash-3.2-safe; do not "fix" them.

## Rule 2: Shared Repo = Check the Staged Set Before Every Commit

`git add <my-file>` does NOT mean only your file is staged. Sibling sessions
(and cron jobs) stage files concurrently into the SAME index. A plain
`git commit` sweeps EVERYTHING staged — foreign work lands in your commit and
its author panics ("my edits vanished").

- [ ] Immediately before committing: `git status --short` AND
      `git diff --cached --name-only`. Review the FULL staged set.
- [ ] Unstage anything not yours: `git restore --staged <file>` — index-only,
      worktree content untouched.
- [ ] NEVER blanket-revert (`git checkout -- .`, `git reset --hard`) in a repo
      others use — you destroy their uncommitted work.
- [ ] After a soft reset, everything returns to the index; separate again with
      `git restore --staged` per foreign file.
- [ ] Backup worktree content to /tmp FIRST (`sha256sum` verify) before any
      recovery dance — proof nothing was lost.
- [ ] Verify against origin: `git rev-parse HEAD origin/main`,
      `git branch -r --contains <sha>`. A sibling may have pushed a commit that
      absorbed yours — confirm the final state on origin rather than fighting it.

## Rule 3: Enforcer Test Contamination While Holding a Lock

`tests/test_runtime/test_governance_bypass.py::TestHasGovernanceLock`
(corrupted/deleted lock → False) FAILS when your session holds an active
governance lock: `_has_governance_lock()` Phase 3 reads the repo marker
`.hermes-cortex/.governance-lock` written by `begin_change`, so it returns True.

- Prove contamination: `mv .hermes-cortex/.governance-lock /tmp/x` → tests pass
  → `mv` back. Phase 1 primary lock is separate, so your write gate survives.
- Never call these a regression while mid-lock.

## Rule 4: PENDING Cycles — Yours vs Others

- `begin_change` creates a PENDING cycle. The doctor distinguishes (since
  2026-08-05, commit 63981498): a cycle whose task_id has a LIVE lock file
  (`~/.hermes-cortex/state/.governance-*.json`, status executing) is the
  CURRENT task → reported INFO "score at end_change", NOT a FAIL. A cycle
  whose task_id has NO lock is a LEAK (you moved on without scoring) → FAIL.
  Green is achievable mid-lock; the current task's own cycle no longer fails
  the doctor.
- Score ALL your own cycles (`feedback_accept`) before `end_change` — and
  score each task's cycle at THAT task's end_change. NEVER batch: opening
  `begin_change` under a new task_id while earlier cycles from the same
  session are still PENDING creates a leak (Luke caught 3 such cycles
  2026-08-05; the 30-min backlog alert fires on exactly this).
- Do NOT score a sibling session's or cron's cycles while they are paused or
  mid-work — they own those. Enumerate with `cycle_query(status="pending")`,
  score only the ones your session_id created.
- `cortex-update.sh` purges governance locks (Pitfall 2) — re-acquire with
  `begin_change` after deploy.

## Rule 5: Rebase/Cherry-Pick/Revert False "no-verify" Flag — FIXED via Reflog Discriminator (2026-08-04)

**Symptom:** `git pull --rebase` replays your commit WITHOUT running the
pre-commit hook, so the pre-commit sentinel (`.git/.pre-commit-ran`) is never
written. The post-commit hook then logs the NEW rebased hash in
`~/.hermes-cortex/state/no-verify-log.json` as a `--no-verify` commit, and
pre-push BLOCKS your push: "commit X was made with --no-verify". Cherry-pick
and revert hit the same false positive. It's a FALSE POSITIVE — the commit
went through the hook originally; the replay just bypassed it mechanically.

**Root fix (committed 7bc86ca3):** `post-commit-audit` now discriminates via
the HEAD reflog message instead of assuming sentinel-missing == bypass:

- `git reflog -1 --format='%gs'` — genuine `git commit` (normal, `--no-verify`,
  `--amend`, `--fixup`) ALWAYS writes a message starting with `commit`
  (`commit: ...`, `commit (amend): ...`). Internal replays write something
  else: `rebase (pick): ...`, `cherry-pick: ...`, `revert: ...`,
  `merge <branch>: ...`, `pull ...:`.
- Logic: missing sentinel AND reflog starts with `commit*` → genuine bypass →
  LOG. Missing sentinel but reflog is a replay prefix → silent, no log entry.

**⚠️ Pitfall — use `commit*`, not `commit:`.** The first implementation used
the prefix `commit:` which does NOT match `commit (amend): ...` — so
`git commit --amend --no-verify` (a GENUINE bypass) would have slipped through
silently. Prefix matching must be `commit*` so amend/no-verify still logs.
A real bypass must never be silenced to fix a false positive.

**Workaround still needed ONLY on hosts whose deployed post-commit predates
the fix** (before the next `cortex-update.sh`): `git commit --amend --no-edit`
re-runs the full pre-commit hook (sentinel written → consumed cleanly),
producing a new hash NOT in the log; then push passes. Leave the old dangling
entry — it can never match a future push range, and deleting audit entries
looks like tampering.

**Do NOT:** `rm ~/.hermes-cortex/state/no-verify-log.json` to unblock a push —
that is exactly the audit-trail tampering the pre-push hook exists to catch.

**Verify hook behavior with the 8-path matrix** before shipping any hook
change that touches the sentinel: `scripts/test-post-commit-sentinel-matrix.sh`
builds a scratch repo, installs the real hooks, and runs all eight paths
(normal, --no-verify, rebase, cherry-pick, revert, merge, amend, amend
--no-verify) asserting which must log and which must stay silent.

## Rule 6: Hooks Run in EVERY Repo — Never Assume the Cortex Tree

`core.hooksPath ~/.hermes-cortex/hooks` is set **globally** — the pre-commit/
pre-push hooks fire in every git repo on the host (client-mwi, client-works,
client repos, any project without the cortex `ops/` tree). A hook that builds
a path on `$REPO_ROOT` (the repo being committed IN) and assumes cortex
layout breaks EVERY commit in those repos — even one-line test fixes.

**Real regression (2026-08-04, Esther, commit `faa0e929`):** the adversarial
gate hard-resolved `ADVERSARIAL_SCRIPT="$REPO_ROOT/ops/scripts/quality/adversarial-verify.py"`.
That path exists only in ~/hermes-cortex itself. Project repos have no `ops/`
tree → fail-closed block on every commit (Titus hit it on client-mwi within
hours). Fix `72d6cdc3`: candidate loop with deployed-path fallback.

**The pattern — repo-local first, canonically-deployed second, fail CLOSED:**

```bash
ADVERSARIAL_SCRIPT=""
for candidate in "$REPO_ROOT/ops/scripts/quality/adversarial-verify.py" \
                 "$HOME/.hermes-cortex/scripts/adversarial-verify.py"; do
  if [[ -f "$candidate" ]]; then
    ADVERSARIAL_SCRIPT="$candidate"
    break
  fi
done
if [[ -z "$ADVERSARIAL_SCRIPT" ]]; then
  # fail CLOSED — a commit without the scan is a bypass
  exit 1
fi
```

- `$HOME/.hermes-cortex/scripts/` is where `cortex-update.sh` registers every
  deployed tool on BOTH Linux and macOS — always include it as the fallback.
- `$REPO_ROOT` (from `git rev-parse --show-toplevel`) is the repo being
  committed IN — only valid as the FIRST candidate, never the only path.
- The existing score-cycle lookup (line ~576) already had this pattern — the
  adversarial block just didn't follow it. **When adding a tool lookup to a
  hook, copy the established candidate-loop pattern, don't invent a new one.**

**Verify BEFORE shipping a hook change (all three):**
1. Commit in the cortex repo → repo-local candidate wins (scan runs)
2. Commit in a scratch project repo with NO `ops/` tree → deployed copy found
   (`git init /tmp/proj && git config core.hooksPath ~/.hermes-cortex/hooks`)
3. Temporarily move the deployed tool aside → commit still blocked (exit 1),
   then restore

## Rule 7: Test Enforcement Gates with DIRECT Tool Calls — Never Subprocess-in-Script

The enforcer gates the TOP-LEVEL tool call only. Putting the command under test
inside a bash script (`bash /tmp/test.sh` whose body runs
`git commit --no-verify ...`) means the enforcer sees `bash /tmp/test.sh` —
the inner git command runs as a subprocess and NEVER crosses the gate. A test
that "proves" the gate is broken this way is testing nothing (2026-08-05: a
false "bypass-debt gate not working" conclusion; the gate was fine).

- Run the exact command as a **direct terminal call** (`cd /tmp/repo && git
  commit --no-verify ...` — hold a governance lock so the outer call passes),
  and expect the gate's block message.
- For compound commands, the enforcer evaluates the WHOLE string — a
  `python3 -c '...' ; git commit --no-verify ...` one-liner is gated as one
  unit, so set up state (debt file, marker) in a SEPARATE call first.
- Unit-test the gate's classifier functions directly by importing the deployed
  module (`spec_from_file_location` on
  `~/.hermes/plugins/governance-enforcer/__init__.py`) and calling
  `_is_readonly_terminal_command`, `_bypass_debt_count`, `re.search(...)` —
  fast, deterministic, no repo needed.

## Rule 8: Content Scanners Need Narrow Path Exemptions for By-Design Data Files

PII/content scanners (enforcer PII gate, secret-leak-detector) must exempt
files whose PURPOSE is to hold the flagged content — with a NARROW path
allowlist, never a blanket pattern disable. The shared blocklist
(`ops/install/deploy/nginx/blocked_ips.add` / `.submit`) exists to hold PUBLIC
IPs; that is the data, not PII. Without the exemption every commit staging the
file warns once per IP — Gisu got flooded with dozens of `⚠ PII — public IP
address` warnings per commit (Telegram spam-filter ban risk), and the
pipeline's own sanctioned commits generated the noise too (2026-08-05).

- Exempt by exact repo-relative path (`case "$FILE" in ...blocked_ips.add|...blocked_ips.submit) : ;; *) ...scan... ;; esac`).
- Everything else must stay scanned — the exemption is a 2-line case, not an IP pass.
- Prove RED-GREEN: same IPs in the exempted file → 0 warnings; same IPs in a
  normal file → warnings still fire.

## Rule 9: Pinned Repos + the hooksPath Guard — Refresh Files AND Carve Out the Guard

`pin_repos_with_own_hooks()` sets a repo's local `core.hooksPath` to its OWN
`.git/hooks` (to preserve deploy-bare-repo hooks) but historically never
refreshed the hook FILES — stale copies predated the mandatory adversarial
gate (Titus audit 2026-08-05: 9 repos, `grep -c adversarial = 0`). Two things
are needed together, or the fix breaks commits:

1. **Refresh the files**: `cortex-update.sh` `refresh_pinned_hook_files()`
   copies the 4 cortex hooks (pre-commit-score, pre-push-pull,
   post-commit-audit, post-push-audit) from deployed source into the repo's
   own hooks dir. ONLY files carrying the cortex banner (`Git <type> hook`,
   ASCII match — locale-safe on macOS) are overwritten; foreign hooks (vllm
   pre-commit framework shim) are preserved. Missing hook files get the gate
   installed.

2. **Carve out the hooksPath guard**: pre-commit-score and pre-push-pull both
   fail CLOSED when `core.hooksPath != ~/.hermes-cortex/hooks` (5ab54547).
   That guard would block EVERY commit in a pinned repo (their hooksPath IS
   their own dir). The carve-out passes when the hooks dir carries any
   cortex-managed hook (governance IS running there); the tripwire still
   fires when hooksPath points at a dir with no cortex hooks.

**Verify before shipping a pinned-hooks change (all three):**
1. Scratch repo with stale cortex hook → after refresh, copy byte-matches
   deployed and commit passes the hooksPath guard (fails later at the
   governance lock — that's fail-closed working)
2. Repo with a FOREIGN hook → refresh skips it, hash unchanged
3. Doctor `Pinned hooks fresh` check: FAIL on stale → refresh → PASS

**Pitfall:** deployed hook files are chattr +i immutable — you cannot
overwrite them by hand to test; use `cortex-update.sh` or test with
repo-source as the simulated deployed source.

## Rule 10: Leaked PENDING Cycles Must Block the Push — and Doctor-Output Greps Are Traps

When a gate greps doctor output, the FAIL-detection pattern has bitten twice
(2026-08-05, both caught by the dogfood loop itself):

- **Never grep for the literal word `FAIL`.** The doctor's summary line is
  `❌ Overall: FAILING` — which *contains* "FAIL" → false positive on every
  green run. And `❌ PENDING cycles` contains no "FAIL" → false negative.
- **Never bare-grep `❌` either.** The footer `🔧 REQUIRED ACTIONS — resolve
  each ⚠️ or ❌ above` *contains* ❌ mid-line → counted as a failure. The
  gate blocked its own push showing "1 failure" while printing zero detail.
- **Correct pattern** (both pre-push gate and cortex-dogfood.sh):
  ```bash
  _DOCTOR_FAILS=$(echo "$DOCTOR_OUTPUT" | grep -E '^ *❌' \
    | grep -vcE 'Overall: FAILING' || true)
  ```
  Match `^ *❌` (lines STARTING with ❌ = actual check lines), exclude ONLY
  the summary line. Unit-test against REAL doctor output including the
  footer — a synthetic fixture without the footer line hides the bug.

**Leaked-cycle enforcement (63981498):** the doctor now FAILs only on cycles
from FINISHED tasks (no active lock for their task_id); the current task's
cycle (lock held) is INFO. The pre-push gate therefore must NOT exclude
"PENDING cycles" lines — a push with leaked prior-task cycles is BLOCKED.
That is the mechanism that makes "clear cycles during cleanup, not later"
(Luke directive 2026-08-05) physical: you cannot ship while old cycles sit
unscored. The same applies to `cortex-dogfood.sh` — its verify step counts
the same way.

## Rule 11: Scope Shared-Hook Gates — Cortex Repo + Orchestrator Host Only

Two Luke corrections (2026-08-05) about gate blast radius. The pre-commit and
pre-push hooks fire in EVERY repo on the host (Rule 6) — so any NEW gate added
to them must be doubly scoped or it will block innocent work in project repos:

1. **Repo scope**: only fire in the hermes-cortex repo itself.
   ```bash
   _REPO_TOP=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
   [[ "$_REPO_TOP" == "$CORTEX_REPO_TOP" ]]   # CORTEX_REPO_TOP=${HOME}/hermes-cortex
   ```
   Non-cortex repos (client-mwi, client-works, ebm-website, pinned repos,
   ...) must NEVER run the hermes-cortex doctor — a failing cortex state must
   not block a client repo's push.
2. **Orchestrator scope**: only orchestrator hosts run orchestrator-level
   gates. Reuse `_detect_orch()` (hostname moses|esther AND home
   `/home/<hostname>`, env-independent — the SAME function pre-commit uses
   for its self-test; copy it, don't reinvent). Non-orch hosts never run the
   doctor gate. `cortex-dogfood.sh` exits 1 with a clear message on
   non-orch hosts.

**Orchestrator-only path arrays must be repo-scoped too (Titus over-block):**
the hardcoded `ORCHESTRATOR_ONLY_PATHS` array had UNANCHORED patterns
(`test_.*\.py$`, `.*_test\.py$`, `.*_spec\.py$`) that fired in every repo —
Titus was blocked committing `apps/api/tests/test_ipi_similarity.py` in a
project repo. The config-driven guard (docs/orchestrator-only-paths.txt read
from HEAD) is the correct repo-aware design: "no config file = no
restrictions". The hardcoded array must be wrapped in the same
`if [[ "$REPO_ROOT" == "${HOME}/hermes-cortex" ]]` gate, and any
cortex-specific path it protects that the config misses (e.g.
`^core/governance/tests/`) added explicitly rather than via unanchored
patterns.

**macOS deploy-script portability (deploy-fix-blocked-ips.sh, 2026-08-05):**
a deploy script that hardcodes Linux assumptions breaks on macOS silently —
the sanctioned fix lands in the wrong dir and the doctor FAIL persists.
- DEST: `/usr/local/sbin` (Linux) vs `/usr/local/bin` (macOS) — the doctor
  check is platform-aware; the deploy script must match it.
- Group: `root` (Linux) vs `wheel` (macOS — no root group).
- Immutability: `chattr/lsattr` (Linux) vs `chflags uchg/nouchg` (macOS),
  each guarded by `command -v` so a missing tool never fails the deploy.
- Sudoers template: list BOTH platform paths — a path that doesn't exist on
  a host simply never matches (harmless dead entry on the other platform).
- Detect platform ONCE at top: `[ "$(uname -s)" = "Darwin" ]`.

## References

- `references/leaked-cycles-and-doctor-grep-2026-08-05.md` — the leaked-cycle
  enforcement design (active-lock split), the doctor-output grep trap with
  exact failing/working patterns, and the repo+orch scoping recipe.
- `references/pre-commit-score-fail-closed-2026-08-03.md` — the incident:
  misread → deletion → revert → correct fail-closed fix, with exact commands.
- `references/macos-fail-closed-hook-2026-08-03.md` — macOS portability of the
  fail-closed hook: deployed-path scorer candidate, `timeout`→`gtimeout`
  fallback, bash-3.2-safe construct list, deploy+verify cycle for both OSes.
- `scripts/test-post-commit-sentinel-matrix.sh` — re-runnable 8-path matrix
  (normal / --no-verify / rebase / cherry-pick / revert / merge / amend /
  amend --no-verify) proving genuine bypasses still log and internal replays
  stay silent. Run before shipping any sentinel-touching hook change.
