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

- `begin_change` creates a PENDING cycle; the doctor reports `❌ PENDING cycles`
  whenever ANY open cycle exists — including your own just-opened one. Green is
  impossible mid-lock.
- Score ALL your own cycles (`feedback_accept`) before `end_change`.
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

## References

- `references/pre-commit-score-fail-closed-2026-08-03.md` — the incident:
  misread → deletion → revert → correct fail-closed fix, with exact commands.
- `references/macos-fail-closed-hook-2026-08-03.md` — macOS portability of the
  fail-closed hook: deployed-path scorer candidate, `timeout`→`gtimeout`
  fallback, bash-3.2-safe construct list, deploy+verify cycle for both OSes.
- `scripts/test-post-commit-sentinel-matrix.sh` — re-runnable 8-path matrix
  (normal / --no-verify / rebase / cherry-pick / revert / merge / amend /
  amend --no-verify) proving genuine bypasses still log and internal replays
  stay silent. Run before shipping any sentinel-touching hook change.
