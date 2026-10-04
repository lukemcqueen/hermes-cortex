---
name: enforcement-change-safety
version: 1.1.0
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
- **Hash with the portable helper, never bare `sha256sum`.** Any hook code that
  hashes a file or git object must call a `_sha256()` helper (sha256sum first,
  `shasum -a 256` fallback, exit non-zero when neither exists) — macOS has no
  coreutils sha256sum, and the fallback already exists as the pattern to copy
  in cortex-update.sh (`_sha256_of`). Grep the hook for bare `sha256sum` calls
  outside the helper before shipping.
- **Watch the silent-empty pipeline (fail-open trap).** In `producer |
  missing-tool | consumer` the pipeline's exit status is the CONSUMER's — a
  missing MIDDLE tool yields empty output and exit 0, so a guard like
  `[[ -n "$HASH" ]] && run-check` silently SKIPS instead of failing. When a
  guard branches on the hash/derived value, an empty value is a skip path by
  construction; if the check must run or fail, treat empty as an error.
- **Test macOS portability from a Linux host with a sandboxed PATH.** Build a
  scratch bin dir containing a `shasum` shim (shell script over `openssl dgst
  -sha256`, parsing the hash with `awk '{print $NF}'`), symlinks to the tools
  the code needs, and NO sha256sum; run the helper under that PATH and compare
  against the real sha256sum computed outside the sandbox. Assert on the
  VALUE, not the exit code (the pipeline-empty trap above). The shim must exit
  non-zero when its backend fails (missing file) — a lenient shim masks the
  helper's fail-closed path. Also probe the no-hasher case (empty bin dir):
  the helper must exit non-zero, never fake a hash.
- macOS ships bash 3.2 — `for-in`, `command -v`, `[[ -z ]]`, `$()` are safe;
  `grep -P`, `mapfile`, `${var,,}` are NOT. Check the whole hook, not just your
  edit.
- The pre-existing hook ALREADY uses `<<<` herestrings and `[[ =~ ]]` — both are
  bash-3.2-safe; do not "fix" them.
- **Never call `sudo` unguarded from a hook or a deploy step.** macOS locks with
  `chflags uchg`, which needs NO root — a bare `sudo` there blocks on a password
  prompt mid-commit, which is a HANG, not a clean error. Linux does need root
  (`chattr +i`), but must use `sudo -n` (non-interactive) so a missing NOPASSWD
  rule fails fast instead of prompting. Branch once on `uname -s`: plain
  `hermes-plugin-lock` on Darwin, `sudo -n hermes-plugin-lock` on Linux — the
  pattern `cortex-update.sh` already uses for its lock handling. A hook runs on
  every commit in every repo, so a prompt here poisons unrelated work.

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
- [ ] **Author identity does NOT separate SESSIONS.** Two sessions of the same agent
      on one host share one git identity, so `git log --author` — and any
      author-scoped review range built on it — cannot tell whose work is whose. A
      concurrent session's `git add`/commit can sweep your staged edits into ITS
      commit, and its commit reads as yours. Before pulling, pushing or deploying in
      a shared tree, check `git status --short` for foreign uncommitted work and
      stand down rather than racing it: a rebase cannot proceed over it, and a
      deploy run beside it can abort mid-way (see Rule 21).

## Rule 3: Enforcer Test Contamination While Holding a Lock

`tests/test_runtime/test_governance_bypass.py::TestHasGovernanceLock`
(corrupted/deleted lock → False) FAILS when your session holds an active
governance lock: `_has_governance_lock()` Phase 3 reads the repo marker
`.hermes-cortex/.governance-lock` written by `begin_change`, so it returns True.

- Prove contamination: `mv .hermes-cortex/.governance-lock /tmp/x` → tests pass
  → `mv` back. Phase 1 primary lock is separate, so your write gate survives.
- Never call these a regression while mid-lock.

### DOGFOOD test contamination (un-deployed enforcer edit)

When you edit `plugins/governance-enforcer/__init__.py` but haven't deployed it
via `cortex-update.sh`, `test_score_gate.py::test_begin_change_refuses_on_decorated_pending_cycle`
fails with `"DOGFOOD REQUIRED"` instead of the expected `"Close out your previous task"`.
This is NOT a regression — the DOGFOOD gate correctly prevents `begin_change` when
repo ≠ deployed. Deploy (`cortex-update.sh`), then rerun: the test passes.

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
- **Before deleting a lock FILE, read its cycle.** A lock the doctor prints as
  `Remove: rm -f ...` may still carry an UNSCORED cycle; deleting the file then
  converts it from "current task" (INFO, expected mid-session) into a LEAK
  (FAIL) that blocks the push. Confirm the cycle's `decision != PENDING` (or
  score it) first. Removing an ORPHANED lock whose cycle is already scored is
  correct cleanup and leaves no leak — check, do not assume either way.
- **`cortex-update.sh` no longer purges live locks (FIXED 2026-08-05).** The
  old "deploy purges locks" behavior was a TIMEZONE BUG, not a feature: the
  stale-lock cleanup sliced the heartbeat to `[:19]`, STRIPPING the ISO-8601
  `Z` (UTC) marker, then `date -d` parsed UTC as LOCAL time — on UTC+9 hosts a
  2-minute-old lock computed as 9h old → deleted on EVERY deploy. See Rule 12
  for the full story. If a deploy still eats your lock, check the stale-lock
  age math FIRST (a fresh lock showing hours of age = TZ bug), then re-acquire
  with `begin_change` as a stopgap only.

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
pre-push hooks fire in every git repo on the host (client-repo-a, client-repo-b,
client repos, any project without the cortex `ops/` tree). A hook that builds
a path on `$REPO_ROOT` (the repo being committed IN) and assumes cortex
layout breaks EVERY commit in those repos — even one-line test fixes.

**Real regression (2026-08-04, Esther, commit `faa0e929`):** the adversarial
gate hard-resolved `ADVERSARIAL_SCRIPT="$REPO_ROOT/ops/scripts/quality/adversarial-verify.py"`.
That path exists only in ~/hermes-cortex itself. Project repos have no `ops/`
tree → fail-closed block on every commit (Titus hit it on client-repo-a within
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
   Non-cortex repos (client-repo-a, client-repo-b, client-web-app, pinned repos,
   ...) must NEVER run the hermes-cortex doctor — a failing cortex state must
   not block a client repo's push.
2. **Orchestrator scope**: only orchestrator hosts run orchestrator-level
   gates. Reuse `_detect_orch()` (hostname moses|esther AND home
   `/home/<hostname>`, env-independent — the SAME function pre-commit uses
   for its self-test; copy it, don't reinvent). Non-orch hosts never run the
   doctor gate. `cortex-dogfood.sh` exits 1 with a clear message on
   non-orch hosts.

**Scoping is not only for NEW gates — audit the EXISTING ones.** A gate written
before the repo guard existed keeps firing in every repo, and one stale cortex
state then blocks ordinary commits in unrelated projects while telling the user
to run a cortex deploy they have no reason to run. The failure mode is
structural and greppable: the gate sits ABOVE the `IS_CORTEX_REPO` assignment
(`REPO_ROOT == ${HOME}/hermes-cortex`), so it is unscoped BY CONSTRUCTION.

- When touching any shared hook, walk every `echo "❌ …"` block and classify it:
  (a) repo-scoped, (b) orchestrator-scoped, or (c) a genuinely universal quality
  gate (syntax, secret scan, adversarial) that SHOULD run everywhere. Anything
  that compares cortex-internal state — the enforcer-drift ("DOGFOOD") check,
  which compares this repo's HEAD enforcer against the DEPLOYED copy — belongs
  in (a): no other repo can act on that divergence.
- If the guard is computed late, either move it above the gate or inline the
  cheap equivalent (`_TOP=$(git rev-parse --show-toplevel)` +
  `[[ "$_TOP" == "${HOME}/hermes-cortex" ]]`) rather than reordering a long
  script. Use the SAME `${HOME}/hermes-cortex` comparison the other cortex-only
  gates use, so there is one scoping idiom to audit.
- Prove it by real execution, not inspection: run the deployed hook from a
  throwaway `git init` repo and assert the gate does NOT fire (the hook still
  runs its universal gates), then confirm it DOES fire in the cortex repo.

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

**Governance audits must probe the same object the lock tool protects —
resolve symlinks before any immutability/permission check.** Hooks like
`hooks/pre-commit` are SYMLINKS to deploy targets (`scripts/pre-commit-score`);
the immutable flag (chattr +i / chflags uchg) lives on the TARGET, and on
macOS `ls -lO` on a symlink reports the LINK's own empty flag field. A check
that probes the symlink path reports "flag missing" on fully-protected files —
a false positive that fires daily until fixed. Every immutability probe must
`realpath()`/`resolve()` first and route through the shared cross-platform
probe (`cortex_doctor/immutability.py`: `lsattr 'i'` on Linux, `ls -lO 'uchg'
on macOS) — never shell to `lsattr` directly (absent on macOS), and never
treat probe failure as "not immutable" (raise → caller WARNs; P12). When a
peer reports "your auditor says X is unprotected", first compare the exact
paths probed against the paths the lock tool actually protects — a contract
mismatch between checker and enforcement tool is the bug class, and the
fix belongs to whoever owns the checker script.

## Rule 12: TZ Bug in Lock-Age Math Kills Live Locks — and Mandatory Dogfood Runs the Deploy

**The TZ bug (2026-08-05, Luke: "this lock issue is MISERABLE"):** the "cortex-
update purges locks every deploy" behavior was NOT a designed purge — it was a
timezone parse bug in cortex-update.sh's stale-lock cleanup:

- The heartbeat is ISO-8601 UTC ending in `Z` (e.g. `2026-08-05T08:42:54Z`).
- The cleanup sliced it to `[:19]` — **stripping the `Z`** — then ran
  `date -d "$heartbeat" +%s`, which parses a marker-less timestamp as LOCAL
  time. On a UTC+9 host (KST) the UTC time parsed as +9h-offset LOCAL → a
  FRESH 2-minute lock computed as **9h old** → `> 3600` threshold → **deleted
  on every deploy**.
- The enforcer's `_has_governance_lock` (Python `datetime.fromisoformat`)
  handled `Z` correctly the whole time — the lock was being deleted under it.

**Fix pattern for ANY bash `date -d` on an ISO heartbeat: KEEP the `Z`** —
`date -d "2026-08-05T08:42:54Z" +%s` parses correctly. Or use Python
(`fromisoformat` handles `Z`). When diagnosing a "purged" lock, verify the
age math FIRST: a lock minutes old showing hours of age = TZ bug, not a real
stale lock. Python purge paths (MCP server, purge-stale-governance-locks.py)
were already correct — but the bash `date -d` had a SECOND, worse bug
(2026-08-10, Titus): **`date -d` is GNU-only** — macOS BSD date has no `-d`,
so the `2>/dev/null || echo 0` fallback fired, epoch=0, age = now-0 ≈ 1.78e9s
> 3600 → **every lock, including fresh v2 session locks, deleted on every
macOS deploy** (cortex-update.sh:2719). The TZ fix (keep the Z) only addressed
GNU parse — the `|| echo 0` was the fail-OPEN trap. Fix that shipped:
portable python3 epoch (`datetime.fromisoformat(hb.replace('Z','+00:00'))`)
with an EMPTY fallback (`|| echo ""`) + `[[ -n "$epoch" ]]` guard — parse
failure now SKIPS the lock (P1-A rule: never delete what you can't
age-verify). **Rule: any heartbeat→epoch conversion in bash must (a) parse
ISO-8601 with Z via python3, not GNU `date -d`, and (b) fail CLOSED on parse
failure — empty string + skip, never `|| echo 0` + delete.**

**Mandatory dogfood in the pre-push gate (Luke: "make this MANDATORY — I
thought you did already"):** a push that touches ANY non-doc file in
hermes-cortex runs the FULL dogfood cycle (pull → cortex-update → doctor →
verify) BEFORE landing. The gate invokes `cortex-dogfood.sh --quiet` itself
so the step cannot be forgotten:

- **Scope (both Luke corrections 2026-08-05):** hermes-cortex repo ONLY
  (dogfood = redeployment of HC — irrelevant to client repos) AND orchestrator
  host only. Docs (`*.md`, `docs/`) exempt — no deployed state changes.
- **Trigger is INVERTED, not an allowlist:** fire on every non-doc file
  INCLUDING path changes/renames/config refs. A narrow pattern list missed
  renamed scripts.
- **Own-task exemption:** the dogfood deploy purges the governance lock (the
  TZ bug's orphan behavior, even after the fix the deploy legitimately
  reloads the enforcer plugin), so the doctor sees THIS session's own cycle
  as "leaked" (no lock). `cortex-dogfood.sh` captures the active task_id
  (`DOGFOOD_OWN_TASK`) BEFORE deploy and exempts exactly that task's cycle
  from the FAIL count — other leaked cycles still fail.
- **Skill reloads are NOT lock-coupled:** the per-session skills marker
  (`state/skills-loaded/<session_id>`) survives deploy; the reload trigger is
  deployed-skill drift → doctor → re-`skill_view`, not lock deletion. Do not
  delete locks to force skill reloads — invalidate the marker instead.

## Rule 13: User-Owned Deploy Destinations — Seed-Guard, Never Hash-Overwrite

A register() dest that is USER-OWNED after install (MEMORY.md, USER.md, any
seed template the user personalizes) must never ride the generic
`needs_update()` hash-overwrite path. A personalized MEMORY.md can never match
its template, so EVERY full-mode deploy (the default; the post-merge hook
auto-runs cortex-update.sh) clobbers it — 7 clobbers in one day (2026-08-05),
saved only by `deploy-backups/*.bak` + manual restore.

The doctor made it worse — an INVERTED check: `check_deploy_checksums`
Category 1 parses every `register ` line and content-compares deployed vs repo.
Personalized memory → FAIL + "Run: cortex-update.sh to resync", which is
EXACTLY the destructive action. The broken state (blank seed) PASSED; the
healthy state (personalized) FAILED. Do NOT "fix" the doctor FAIL by resyncing —
fix the classification: user-owned files are not repo-managed files.

Fix pattern (both layers or the bug persists):
- **Deploy**: `register_seed()` — copy ONLY when dest is missing, in BOTH full
  and delta modes. Keep seed dests out of MAP/ORCH_MAP, and cover them in
  `clean_stale_deploys` / `check_stale_deploys` so they aren't flagged stale.
- **Doctor**: parse `register_seed` lines as existence-only — PASS if present,
  WARN if missing, NEVER content-compare a user-owned file.
- A "guarded — only if dest missing" comment on a plain `register` line is a
  LIE until the code enforces it — the false comment is how this bug hid.

**Topology for diagnosis:** live memory = `~/.hermes/memories/MEMORY.md`
(Hermes resolves `get_hermes_home()/memories`, default `HERMES_HOME=~/.hermes`).
The deploy target `~/.hermes-cortex/memories/MEMORY.md` is a dead seed copy on
most hosts — live only when `HERMES_HOME=$HOME/.hermes-cortex` (commented
option in `hermes-cortex.env.example`) or `~/.hermes/memories` is symlinked to
it. Check which path the host loads BEFORE diagnosing "memory wiped": a
checksum "fix" on the dead copy is a no-op; on the live copy it is data loss.

## Rule 14: Per-Session Skill Enforcement + Hook-Override Gate + Close-Out (2026-08-08)

Three governance gaps found and closed by the 2026-08-08 edge-case audit
(Esther, Luke: "test governance thoroughly, see the weaknesses"):

**14a. Skills tracking was PROCESS-global — sessions leaked each other's loads.**
`_skills_loaded_in_session` is one module-level set shared by every session in
the gateway process. Any session's `skill_view()` counted for ALL sessions:
- The 7-skill marker auto-created for a session that loaded only 2 skills
  (other sessions contributed the rest) → write tools unblocked without the
  session actually loading the skills.
- The domain gate (`_check_domain_skill_gate`) and adversarial gate passed
  because ANOTHER session had loaded the skill → on long turns agents never
  loaded mid-turn domain skills; the gate passed anyway.
Fix: per-session registry `_session_skills_loaded: dict[str, set]`, populated
in the pre_tool_call hook on `skill_view`, consulted by the marker auto-create
condition, domain gate, and adversarial gate. Each session must load its own
7 always-skills and its own domain skill. Tests:
`TestPerSessionSkillIsolation` (marker + adversarial) and
`test_md_write_blocks_when_skill_loaded_by_other_session` (domain gate).

**14b. `git -c core.hooksPath=...` / `GIT_CONFIG_GLOBAL|SYSTEM=...` bypassed the
entire hook chain.** The bypass-debt regex only matched literal `--no-verify`.
A per-invocation `-c core.hooksPath=/dev/null commit` skipped EVERY hook
including post-commit-audit, so the debt counter never incremented and the
escape hatch was unbounded. Fix: the enforcer now blocks hook-override forms
outright (they are not the sanctioned escape hatch); `--no-verify` remains
bounded by the debt counter (3 tolerated, 4th+ mandated). Benign `-c` configs
(`user.name`, `color.ui`) and plain `git commit`/`status` are NOT matched.
Tests: `TestGitHookBypassGate` (10 override forms detected, 7 benign forms
clean).

**14c. Sessions could stack unbounded PENDING cycles.** `end_change()` only
WARNED when the task's cycle was unscored, then released the lock; `begin_change()`
only checked for an existing lock. Sequence begin(A) → end(A) unscored →
begin(B) succeeded, leaving A PENDING until the doctor blocked the push.
Fix (Luke: "agents close out/score before moving to a new task"):
- `end_change()` BLOCKS releasing the lock while the task's latest cycle is
  unscored (`user_overrode IS NULL`, decision PENDING/LOOP).
- `begin_change()` REFUSES a new task while THIS session still has unscored
  PENDING cycles (hook cycles with `session_id NULL` are exempt).
Tests: `tests/test_runtime/test_mcp_closeout.py`
(TestEndChangeRequiresScoredCycle, TestBeginChangeCloseOutGate).

**14d. `_skills_dir()` resolved to a NONEXISTENT dir when HERMES_HOME is set —
the fingerprint gate was a constant in production.** The gateway runs with
`HERMES_HOME=/home/<user>/.hermes`; `_skills_dir()` returned
`HERMES_HOME/.hermes/skills` = `~/.hermes/.hermes/skills` (no such dir), so
`_skills_fingerprint()` hashed eight EMPTY mtimes — a constant that never
changed. Markers never went stale after deploys, so agents were never forced
to reload the always-skills mid-turn (the 2026-08-05 skills-before-task gate
was silently dead). Also, `task-start` lives under `workflow/`, which the
fingerprint candidate paths missed. Fix: `_skills_dir()` resolves
`HERMES_HOME/skills` when it exists (HERMES_HOME IS the .hermes dir), and the
candidate list includes `workflow/`. Regression tests: `TestSkillsDirResolution`
(3 env variants + content-vs-mtime fingerprint).

**14e. The fingerprint hashed MTIMES, so a no-op redeploy wiped session credit
(2026-09-23).** `cortex-update.sh` rewrites deployed skill files, moving their
mtimes even when the bytes are identical. That changed `_skills_fingerprint()`,
which discarded the per-session credit journal and invalidated the 7/7 marker
mid-task: the agent saw "7/7 loaded ✅ but still blocked" with nothing wrong on
its side. Live proof on moses — the deployed and repo copies of
`test-driven-development/SKILL.md` were `diff`-identical while the deployed mtime
had moved 15:42 → 15:56. The old rule also had a 1-second blind spot: a
same-second content change did not move the fingerprint at all (the gate missed
real changes while failing on fake ones). Fix: hash CONTENT
(`_skill_content_hash()`, memoized on mtime+size), keep credit per SKILL in the
journal (`hashes` map) so only a skill whose bytes changed loses credit, and
name those skills in the block message via `_stale_skills()` — a weak model
reloads one skill instead of seven. Legacy journals (no `hashes`) keep the old
all-or-nothing rule, fail closed. Regression tests:
`tests/test_runtime/test_skill_content_fingerprint.py` + the probe's "no-op
deploy must not wipe credit" section.

**Checklist when touching these paths:**
- [ ] Per-session skill tests: session A's loads never satisfy session B
- [ ] Hook-override regex: override forms block, benign `-c`/plain git pass
- [ ] Close-out: unscored end_change keeps the lock; begin_change refuses
      with prior PENDING; scored flow releases cleanly
- [ ] Hook cycles (session_id NULL) never trip the begin_change gate

## Rule 15: Fix-Apply Scripts Need a Four-State Guard — "Upstream Removed It" Is Fixed, Not Fail

Scripts that re-apply a local patch to upstream code after every deploy (e.g.
`apply-mcp-tool-watch-fix.py`, `install-lean-index.py`, `install-cron-cost-tracking.py`)
must handle four states when deciding whether to apply:

1. **Already fixed** (marker or corrected pattern present) → SKIP, exit 0
2. **Upstream removed the mechanism entirely** (probe function name absent from the
   file) → SKIP, exit 0 — the bug is structurally gone; nothing to patch.
3. **Buggy pattern still present** → APPLY, exit 0
4. **Neither pattern matched** → FAIL, exit 1 — genuinely unknown state; needs human
   inspection.

**Never exit 0 on "unknown" — that reduces governance by masking a drifted pattern
that needs eyes on it.** The two-state original (fixed? → skip; buggy? → apply;
else → fail) cannot tell "upstream refactored the mechanism away" from "the textual
pattern drifted." The false-positive FAIL blocks the entire deploy tail under
`set -euo pipefail` fleet-wide until an operator manually inspects and overrides.

**Trigger:** the script has an `_is_fixed()` or equivalent check for a specific
multiline pattern string, and the only other path is a catch-all FAIL. If upstream
could ever remove the feature being patched, add the "removed" guard before the
catch-all. The cost of a false SKIP (no-op apply on an already-absent patch target)
is zero; the cost of a false FAIL (blocked deploy, doctor red, every host blocked)
is fleet-wide. The probe check must be sufficiently unique — a function name that
only appears as a def or assign, not a bare string that could appear in a comment
or error message independently.

When adding this guard to `_status()` too, ensure exit 0 on "removed" mirrors
the apply path so automated checks (`--status` pollers, doctor probes) stop
flagging the host.

Implementation pattern in Python:

```python
def _is_probe_removed(src: str) -> bool:
    return "probe_function_name" not in src


def _apply() -> bool:
    ...
    if _is_fixed(src):
        print("SKIP: already applied")
        return True
    if _is_probe_removed(src):
        # Upstream removed the mechanism entirely — bug structurally gone.
        print("SKIP: mechanism removed upstream — nothing to fix")
        return True
    if BUGGY not in src:
        print("FAIL: probe pattern not found — upstream may have changed "
              "the surrounding code. Inspect manually.")
        return False
    # ... apply fix ...
```

## Rule 16: Enforcer Block-Message Changes — Two-Gate Contract + Test Pattern

The skills gate and the lock gate block the SAME write tools with two
independent messages. Agents that fix one gate and then get blocked by the
other conclude the system is broken. When touching either block message:

- **Preserve (or extend) the gate cross-reference.** Every block message must
  label its gate ("GATE 1 of 2" / "GATE 2 of 2"), state that the OTHER gate
  still applies, and name the other gate's remedy — loading skills does not
  satisfy the lock, and an active lock does not satisfy the skills gate. A
  message that describes only its own gate is a defect.
- **Explain write-capable classifications in the block itself.** A terminal
  command with compound metacharacters (`; | & > < \` $()`, newline, or
  interpreter forms like `python3 -c`) is treated as write-capable even when
  it only reads — the lock-gate message must say WHY when this fires
  (condition the note on the same metachar regex the gate uses) and point at
  the read-only alternatives: single clean commands and
  read_file/search_files.
- **Test block messages through register(), not mocks of the closure.**
  Existing hook tests stub the enforcement flow and never exercise message
  text. Build the real hook via a minimal ctx mock (`register_hook` captures
  `pre_tool_call`) with `GOVERNANCE_STATE_DIR` pointed at a temp dir, call it
  with `session_id=`, and assert on the message: gate label present, other
  gate's remedy present, and — for the compound note — silent on clean
  non-terminal writes. Watch it fail before editing the message.
- **Load adversarial-verifier BEFORE pushing enforcement-path changes.** The
  pre-push gate checks the skill was loaded THIS session (per-session
  enforcement, Rule 14a) — a push after commit fails with "ADVERSARIAL
  VERIFICATION REQUIRED" until one `skill_view('adversarial-verifier')`.
- **Order for enforcer changes: commit → dogfood (`cortex-dogfood.sh
  --force`) → push.** The push gate fails "Deploy sync / Plugin content"
  until deployed == repo, and only dogfood syncs the deploy. Docs-only
  changes skip dogfood, but an enforcer `.py` change never does.
- **Deploy ≠ loaded.** cortex-update.sh puts new message text on disk; the
  running gateway keeps the OLD in-memory enforcer until an operator restarts
  it from a separate shell — verify the deployed file's content directly
  (grep the new strings) instead of expecting the live gate to show them.

## Rule 17: Essential Gates Are Event-Driven, Never Cron-Swept — and Fail Loud, Never Silent

An essential governance gate (adversarial review, mandatory verification) must
fire in the COMPLETION path (e.g. `end_change`), not as a scheduled cron sweep.
A cron can be strike-paused after repeated failures — silently disabling the
gate with no alert — and it carries latency between the work and the review.
An event-driven gate fires immediately and can refuse the completion.

- When the gate's dependency is down (reviewer unreachable, scanner missing,
  key unset), REFUSE the completion with a loud error — never silently skip.
  "Essential to governance ALWAYS" means degradation must be visible, not quiet.
- Complexity-gating ("only review non-trivial work") is legitimate
  friction-reduction, but the complexity signal must be MEASURED, never
  self-reported. A worker who gets to declare its own work "trivial" will
  declare trivial. Measure the diff — added+removed lines counted separately
  (a net-zero rewrite is still complex), files touched, untracked new files
  (`git ls-files --others` — `git diff --numstat` omits them) — plus a
  size-independent always-review path list for enforcement/security surface.
- Keep the gate independent even when event-driven: the reviewer runs with a
  fixed committed prompt and a distinct model in a process the worker cannot
  reach, so being triggered by the worker's own close does not let the worker
  grade itself.

## Rule 18: Optional Steps Never Abort the Critical Sync — Defer, Then Exit Loud

A deploy script under `set -euo pipefail` ends on ANY `exit 1`. Order therefore
matters: file sync, the enforcer plugin deploy, and the git-hook install are
CRITICAL (they are what clears enforcer drift and DOGFOOD drift); DB schema
migrations are optional, dependency-bound, and retryable. When a migration sits
BEFORE a critical step and hard-exits, a database that is merely restarting
(`container is restarting`) aborts the whole deploy — the enforcer is never
refreshed, and the stale-enforcer gate then blocks every repo on the host while
the user chases the wrong problem.

- **Never `exit 1` from a step whose failure leaves the host no worse for
  running the rest.** Append it to a `_DEFERRED_FAILURES` array, `error` the
  message, and CONTINUE.
- **Re-check at the END of the flow**, after the critical sync: if the array is
  non-empty, list every failed step and `exit 1`. The non-zero exit still tells
  automation the deploy was incomplete — the point is only that it happens AFTER
  the sync, so no host is left with a stale enforcement chain.
- **Guard the expansion for `set -u`**: test `${#arr[@]} -gt 0` before
  `"${arr[@]}"` — bash 4.0–4.3 error on an empty array expansion under `set -u`,
  and the guard is what keeps the same code correct on macOS.
- **Expect repo≠deployed doctor FAILs mid-change.** After editing a deployed
  script and before running the deploy, the doctor's checksum checks report that
  file as drifting. That is the check WORKING; it clears on the next
  `cortex-update.sh`. Do not "fix" it by reverting the edit or weakening the
  check, and do not report it as a regression.
- Same family as Rule 1 and Rule 15: the goal is never a silent green — it is a
  LOUD failure that does not take the enforcement chain down with it.

## Rule 19: A Fleet-Wide Gap Needs a CHECK, Not Just a Doc

Documentation tells an agent HOW to do something; it never tells it THAT the
work is outstanding. An agent only loads a skill it already knows it needs, and
only opens a runbook that something else points it at — so a migration, or any
change every host must apply, will sit undone however well it is written up.
When asked "will agents know what to do?", the honest answer about docs alone
is NO.

- **Pair every fleet-wide change with a check that reports the gap from the
  host's own evidence** — a doctor check that computes the expected state and
  names the shortfall, so each agent discovers it on its next routine scan with
  no message to lose. A dispatch/message is a one-shot nudge: a host that
  misses it, or that bootstraps later, learns nothing.
- **Make applicability and the deliberately-left-alone set explicit, or the
  check becomes ignored noise.** Skip where the mechanism does not apply at all
  (platform gate — do not warn forever about something the host cannot use),
  and treat a resource the change intentionally did NOT touch as satisfied (a
  unit file in ANY state means the job was considered, so a paused-for-a-reason
  job is never flagged).
- **Prefer WARN over FAIL while nothing is broken yet** — the host still works,
  it is merely un-migrated — and put the runbook path in the remediation field
  so the report is actionable on its own.
- **Mirror the migration's OWN predicate rather than re-deriving it.** Import or
  copy the function that decides eligibility, so the check and the tool can
  never disagree about what is in scope; a hand-written second definition drifts
  from the first one silently.

Same family as Rules 17 and 18: enforcement that is invisible, or that arrives
as prose rather than as a check, is not enforcement.

## Rule 20: Reduce FRICTION, Never Enforcement (Luke directive)

"Make sure you're not reducing governance — but reduce friction to get the work
done." Every governance change trades the two, and the failure mode is reaching
for the wrong one because it is quicker:

- **Never the control.** Not a relaxed test assertion, not an inline
  `adversarial-ignore` on a critical/high finding, not `warn + exit 0` where a
  refusal belongs, not a widened "latest session" lookup used to dodge a session
  key mismatch. Each is small, plausible, and permanent.
- **Always the interface.** Add the missing wiring, make the failure message name
  the fix, register the tool so it actually deploys, and make the recorder
  automatic instead of asking every agent to remember a manual call.
- **Catching yourself mid-weaken and restoring it is normal; hiding it is the
  violation.** If you loosened an assertion to get a suite green, say so and
  assert the real contract instead — exit code AND the message agreeing.
- **A gate that cannot verify must REFUSE — but say what that costs.** Moving a
  gate off a local file onto a shared store adds a dependency; state it plainly
  (a store outage now blocks every commit) and let the user overrule it, rather
  than quietly failing open.

**Transitional bridge — how to ship a gate re-point without an outage.** When the
new writer cannot be live yet (it needs a gateway restart, an operator, or a fleet
rollout) and flipping the gate would fail every commit in the window: while the new
store has NO row for the session, accept evidence from a strictly NARROWER artifact
that is ALSO yours — never from the incumbent you are replacing. Bridging back to
the old source keeps it load-bearing and hides your own writer's failure, which is
the whole thing being removed. Mark the bridge in code as transitional with its
deletion condition, name it in the delivery, and delete it once the real writer is
proven live.

## Rule 21: A Deploy That Dies Mid-Run Leaves the Immutable Layer OPEN

`cortex-update.sh` unlocks the enforcement targets EARLY and relocks them LATE, after
the deployment steps, with no EXIT guard. Any run that exits non-zero or is killed in
between — a `set -euo pipefail` abort like Rule 18 describes, a timeout, a stop —
leaves the enforcer plugin, the hooks, the gate scripts and `loop-gov-mcp.py`
WRITABLE. Nothing announces it; the governance auditor reports it later.

**Detect (read-only, no lock needed):**

```bash
hermes-plugin-lock status    # nine lines. `----i---` = locked, `--------` = UNLOCKED
```

**Fix — and do not over-think the permissions:**

```bash
sudo -n /usr/local/sbin/hermes-plugin-lock lock
hermes-plugin-lock status | grep -c -- '----i'    # expect 9
```

- **Never probe with `sudo -n true`.** `/bin/true` is named by no command-specific
  rule, so it answers "a password is required" on a host where the lock helper IS
  granted. That false negative reads as "passwordless sudo is broken" and sends you
  designing workarounds for a grant that was never missing. Probe the exact path you
  intend to run: `sudo -n /usr/local/sbin/hermes-plugin-lock status`.
- **Read the deploy log WHOLE — count both sides.** A healthy run logs `Locking
  enforcement files…` plus ~63 `LOCKED:` lines, and the relock sits AFTER the last
  `UNLOCKED:` line. A `head`/`tail` view of a long log shows the unlocks and hides
  the relock, which reads as "the deploy never relocked" when it did.
- **A deploy that died this way leaves a stale `.running` marker under
  `state/pending-update-results/` with no live process.** Do NOT delete it: the
  handler sweep declares it dead after ~30 minutes and reports a timeout result, and
  removing the marker silently converts a reported-dead deploy into an
  apparently-successful one.
- **Unlocked is not tampered.** Check the doctor's checksum checks before assuming
  corruption — the flag goes missing, the content does not. Report it as a protection
  gap, not as file damage.
- **Fail-safe direction for any unlock/relock window:** relock on EXIT, not only on
  the success path. A guard that only relocks when the run completes is a lock that is
  off precisely when the deploy failed — the worst case.

## Rule 22: The Adversarial Verdict Is FROZEN Per Cycle — Make Your Work VISIBLE First

`end_change()` on a complex change runs an adversarial review whose verdict is
stored ONCE per cycle. A `FINDINGS` verdict does not refresh: calling
`end_change()` again re-reports the identical findings verbatim, quoting the
ORIGINAL note. The refresh path is `rereview_change` (a NEW note plus the
evidence that changed) — and where that tool is not registered on the deployed
server ('Unknown tool'), the cycle cannot close without `feedback_override`,
which is exactly the escape hatch that must not be used to escape a review.
Report the deadlock as a governance defect (record an issue, name the missing
tool) and let the lock sit until TTL; do not override to get a green close.

- **Untracked files are INVISIBLE to the reviewer.** It reads the staged/diff
  window, so a new file you never `git add` reads as "claimed but absent" → the
  reviewer files a **fabrication** finding against your own note. Stage your work
  (or paste raw command output, exit codes and resolved paths into the cycle
  note) BEFORE `end_change`. A summary such as "tests pass / the resolver
  confirms it" is unsupported self-report by construction.
- **The same window picks up OTHER sessions' commits.** Commits landing in the
  repo while your cycle is open appear in the material, so findings can target
  work you did not author. Classify every finding against your OWN staged set
  before accepting it: state plainly which findings are not yours (and why), with
  the evidence — `git show --stat` on the peer's commit, and the absence of the
  file from your staged set.
- **A frozen verdict is fixable only at the source.** When the reviewer's
  findings keep citing a file outside your change, the real defect is window
  scoping (review the session's own reported/staged set, not every commit in the
  range). File it as an issue rather than bending your change to satisfy it.

## Rule 23: Preserve Enforcement Behaviour by DIFFERENTIAL PROBE, Not by Inspection

Rewriting a matcher, classifier or scanner in enforcement code leaves exactly one
question that matters: does it still decide the same way? Reading the diff cannot
answer it. Load BOTH implementations in one process and run the same inputs
through both:

```python
import importlib.util

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

old = load("enf_old", "/home/<user>/.hermes/plugins/governance-enforcer/__init__.py")   # DEPLOYED
new = load("enf_new", "/home/<user>/hermes-cortex/plugins/governance-enforcer/__init__.py")  # REPO
for case in FIXTURES:
    assert (old.gate(case) is None) == (new.gate(case) is None), case
```

- **The DEPLOYED copy is the oracle.** It is the behaviour currently in force, so
  a mismatch is a real behaviour change rather than a test-authoring choice. Run
  the probe before the commit and again after any follow-up edit.
- **It finds defects the diff review does not.** One real example: `frozenset(some_bytes)`
  iterates the bytes into single-byte INTs, so an "allowed digests" set silently
  held 28 one-byte entries instead of one digest and every case it was meant to
  permit was blocked. Nothing about the diff looked wrong.
- **Keep the probe in the scratch dir.** It has to hold the plaintext and fixtures
  the scanner blocks, so it can never be committed; commit only the derived test.
- Assert on the VERDICT (blocked / allowed), not on message text, unless the
  message itself is the contract.

## Rule 24: A Content Scanner That Scans Its Own Source

Three traps that all appear when the artefact you are editing is subject to the
scanner it implements.

- **A readable deny-list in a public repo is an index of what it protects.** Store
  the terms as digests and hash candidate substrings, so the gate still detects a
  term it never spells out. Keep the entry LENGTHS beside the digests — they bound
  the scan — and slide a window of each length over the content, which preserves
  substring semantics (a term embedded inside a longer token is still found).
- **Pick an encoding the scanner does not itself flag.** A hex digest can contain a
  seven-digit run, which the same module's phone pattern flags when the file is
  written through the gate it implements; base64 of the raw digest is shorter and
  does not collide. Whenever a module's own constants are scanned by that module,
  check the constants against every pattern in it before shipping.
- **Fixtures the scanner blocks cannot be written literally.** A test for a
  phone/PII/host scanner must exercise real-shaped values, and those are exactly what
  the gate refuses to let you write. Assemble them at runtime from parts, and prefer
  DERIVING a real value from an already-public source in the repo (parse the owner
  handle out of the README's own URL) over restating it — that keeps end-to-end
  coverage of the real deny-list with no new literal, and the same technique lets the
  write itself pass the gate.
- **Never echo the matched term into the block message.** That message is written
  into logs and transcripts, so name the CLASS ("personal identifier"), never the value.
- **Behaviour-preserving refactors of a deny-list are testable without the terms.**
  Drive the mechanism end to end with SYNTHETIC digests injected through the module's
  own attributes (blocked in prose, allowed inside the sanctioned URL, found inside a
  longer token), and pin the real configuration by cardinality and digest width.

## Rule 25: Judge Repo↔Deployed Drift by CONTENT, Never by mtime

A "deployed copy is newer than repo source" warning (the doctor's `Skill drift`, or
any repo-vs-deployed parity check) is a DIFFERENT condition from "repo changed,
deploy pending", and it never resolves itself: the deploy's drift guardrail SKIPS
any deployed file newer than its repo source, so the content is neither clobbered
nor propagated — it is STRANDED on one host and the fleet never receives it.

- **Reconcile by copying deployed → repo, byte-for-byte, and assert it**
  (`shutil.copy2(deployed, repo)`, then
  `assert repo.read_bytes() == deployed.read_bytes()`). Review each diff first —
  a deployed copy can carry host-specific paths or PII that must not enter a
  public repo.
- **Direction decided by mtime is unreliable: `git clone` and `git checkout` reset
  every repo mtime to "now"**, so a genuinely stranded file is classified
  repo-newer and the check stays SILENT — the one case it exists to catch. Decide
  by CONTENT instead: a file is stranded when its deployed content appears neither
  in the repo working tree nor in any committed revision of that path
  (`git log -n<N> --format=%H -- <path>`, then `git show <rev>:<path>`). Deployed
  content that matches an OLDER commit is a normal pending deploy, not stranding.
- **A deploy banner is not drift.** Deployed `.sh`/`.py` copies carry a 3-line
  `# SOURCE:` banner the repo copy lacks — inserted after the shebang, or at line 1
  when the file has no shebang. Strip it before comparing, or every deployed script
  reports drift.
- **Compare every file, not just the entry point.** A check that only compares
  `SKILL.md` cannot see a drifted `references/` or `scripts/` file.

## References

- `references/memory-seed-clobber-2026-08-05.md` — the memory-clobber root
  cause chain (register comment lie → needs_update hash path → doctor Category 1
  sweep → inverted doctor), the live-vs-seed topology, and the register_seed +
  existence-only doctor fix design.

- `references/tz-bug-lock-purge-and-mandatory-dogfood-2026-08-05.md` — the TZ
  root cause with exact before/after age math, the mandatory-dogfood gate
  scope corrections, and the own-task exemption design.
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
- `references/skill-marker-fingerprint-invalidation-2026-09-01.md` — the
  "7/7 loaded ✅ but still blocked" loop. A deploy that touches a skill file's
  CONTENT invalidates every session marker (the fingerprint hashes skill
  content since 2026-09-23; it hashed mtimes before, which fired on redeploys
  that changed nothing); recovery is one serial `skill_view` (in-memory set
  intact) or re-loading all 7 (after a gateway restart), and the block message
  now names the exact skills to reload. Includes the docs-drift variant
  (AGENTS.md enumerating the always-set with old names) and the whole-repo grep
  rule when the set changes.
