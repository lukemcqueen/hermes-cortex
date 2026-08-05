# Leaked Cycles, Doctor-Output Greps, and Gate Scoping — 2026-08-05

Session evidence for Rules 4, 10, 11 of enforcement-change-safety. All
commits: 63981498 (leaked-cycle enforcement), 95997d0c (orchestrator-array
repo scope), bf2e8249 (macOS deploy portability).

## 1. Leaked PENDING cycle enforcement (commit 63981498)

**Incident:** Luke's 30-min backlog alert showed 3 PENDING cycles from
`pinned-hooks-dogfood` while I had already moved on to later task IDs. Root
cause: the doctor FAILed on ANY pending cycle — including the current task's
own — so the pre-push gate excluded the whole "PENDING cycles" line. That
exclusion ALSO hid leaked cycles from finished tasks.

**Design:** end_change unlinks the session lock file. So a PENDING cycle
whose task_id has NO active lock file is a leak; the current task's cycle
(lock exists, `status: executing`) is expected.

Lock file: `~/.hermes-cortex/state/.governance-<session_id>.json`
```json
{ "task_id": "...", "status": "executing", "repo_slug": "hermes-cortex", ... }
```

Doctor logic (checks.py check_governance, PENDING cycles section):
```python
_active_tasks = set()
for _lf in (CORTEX_HOME / "state").glob(".governance-*.json"):
    _ld = json.loads(_lf.read_text())
    if _ld.get("status") == "executing" and _ld.get("task_id"):
        _active_tasks.add(_ld["task_id"])
# ...
_current = [r for r in _fresh if r['task_id'] in _active_tasks]   # INFO
_leaked  = [r for r in _fresh if r['task_id'] not in _active_tasks]  # FAIL
```

Verified with an INJECTED fake cycle (insert directly into loop-governance.db
with a fake session_id, run check_governance, then DELETE the row):
- current-task cycle → `INFO  PENDING cycles: 1 active-task cycle(s) (lock
  held): <task>#1 — score at end_change`
- injected leaked cycle → `FAIL  PENDING cycles: 1 unscored cycle(s) from
  finished task(s): fake-leaked-task#1 (fake-session...)` + hint "Score them
  via feedback_accept or cancel with feedback_override BEFORE starting new
  work"

Gate change: pre-push `_DOCTOR_FAILS` grep dropped `PENDING cycles` from its
exclusion list — leaked cycles now block the push. Mid-session push still
passes because the current cycle is INFO (a `^ *❌` line? no — INFO lines are
`ℹ️`, not `❌`, so they never count as fails).

## 2. Doctor-output grep trap (caught twice, both by the dogfood loop)

First attempt: `grep -q "FAIL\|blocking\|ERROR"` on doctor output.
- False positive: `❌ Overall: FAILING` contains "FAIL" → blocked every push.
- False negative: `❌ PENDING cycles` contains no "FAIL" → would miss it.

Second attempt: `grep '❌'` (any line containing ❌).
- False positive: footer `🔧 REQUIRED ACTIONS — resolve each ⚠️ or ❌ above`
  contains ❌ mid-line → counted as 1 failure. The gate printed "Push blocked:
  doctor reports 1 failure" but the detail grep showed NOTHING — the smoking
  gun that the counted line was the footer, not a check.

Working pattern (both pre-push-pull and cortex-dogfood.sh):
```bash
_DOCTOR_FAILS=$(echo "$DOCTOR_OUTPUT" | grep -E '^ *❌' | grep -vcE 'Overall: FAILING' || true)
```

Unit-test MUST use real doctor output including the footer line — a
synthetic fixture without it passes the broken pattern.

## 3. Gate scoping (Luke corrections, 2026-08-05)

The pre-push doctor gate I first shipped ran on EVERY push in EVERY repo
(original code had a `DOCTOR_RELEVANT` case match on cortex_doctor/* paths,
which doc-only pushes bypassed). Luke's two corrections:

1. "This is ONLY FOR HERMES-CORTEX updates... does not apply to non-hermes
   cortex repos" → repo-top check.
2. "really only applied to orchestrators in practice" → _detect_orch.

```bash
_detect_orch() {
  local _host _home _user
  _host=$(hostname -s 2>/dev/null || echo "unknown")
  _user=$(id -un 2>/dev/null || echo "$USER")
  _home=$(getent passwd "$_user" 2>/dev/null | cut -d: -f6)
  _home="${_home:-$HOME}"
  case "$_host" in
    moses|esther) [[ "$_home" == "/home/$_host" ]] && return 0 ;;
  esac
  return 1
}
if [[ "$_REPO_TOP" == "$CORTEX_REPO_TOP" ]] && _detect_orch && [[ -f "$CORTEX_DOCTOR" ]]; then
```

Verified scope matrix (bash harness with _detect_orch stubbed to return 1):
- project repo + test files → ALLOWED (the Titus fix)
- cortex repo + tests/, core/governance/tests/, cortex_doctor/ → BLOCKED
- cortex repo + regular code → ALLOWED

## 4. Orchestrator-only array over-block (commit 95997d0c)

The hardcoded `ORCHESTRATOR_ONLY_PATHS` array in pre-commit-score had
unanchored patterns (`test_.*\.py$`, `.*_test\.py$`, `.*_spec\.py$`) that
matched ANY file anywhere — Titus blocked on
`apps/api/tests/test_ipi_similarity.py` in a project repo. The config-driven
guard (docs/orchestrator-only-paths.txt from HEAD, "no config = no
restrictions") is the correct repo-aware design; the array was a legacy
remnant. Fix: wrap the whole array in
`if [[ "$REPO_ROOT" == "${HOME}/hermes-cortex" ]]`, add
`^core/governance/tests/` (3 live test files the config's `tests/` entry
doesn't cover). Note: `REPO_ROOT` and `STAGED_FILES` are defined earlier in
the hook (config-driven guard section) — reuse them, don't re-derive.

## 5. macOS deploy-script portability (commit bf2e8249)

deploy-fix-blocked-ips.sh hardcoded Linux: DEST=/usr/local/sbin, group root,
chattr/lsattr. On macOS: /usr/local/bin, group wheel, chflags uchg/nouchg.
The doctor check (checks.py) was ALREADY platform-aware — the mismatch
between script and check is what left the FAIL persisting after the
"sanctioned fix" ran. Pattern:

```bash
IS_MACOS=0; [ "$(uname -s)" = "Darwin" ] && IS_MACOS=1
if [ "$IS_MACOS" -eq 1 ]; then DEST="/usr/local/bin/fix-blocked-ips.py"; DEST_GROUP="wheel"
else DEST="/usr/local/sbin/fix-blocked-ips.py"; DEST_GROUP="root"; fi
# helpers: unlock_file/lock_file/is_locked branch chflags vs chattr, guarded by command -v
```

Sudoers template (hermes-security) carries BOTH paths:
```
__SUDO_USERS__ ALL=(root) NOPASSWD: /usr/local/sbin/fix-blocked-ips.py
__SUDO_USERS__ ALL=(root) NOPASSWD: /usr/local/bin/fix-blocked-ips.py
```
Validated with `visudo -c` on the rendered template. A path that doesn't
exist on a host never matches — harmless dead entry.

## 6. Dogfood loop proved the fixes

The permanent dogfood command (cortex-dogfood.sh: pull → deploy → doctor →
verify) + pre-push doctor gate caught each bug in this session:
- blocked its own first push on un-deployed drift (3 checksum/hook-drift
  FAILs) — proving "deploy before push" matters
- caught the footer false-count (push blocked, "1 failure", zero detail)
- the final push of 63981498 passed clean only after all three fixes
