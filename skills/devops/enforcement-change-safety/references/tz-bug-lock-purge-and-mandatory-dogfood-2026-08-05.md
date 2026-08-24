# TZ Bug in Lock Purge + Mandatory Dogfood Gate (2026-08-05)

## The TZ bug — why cortex-update deleted the live session lock every deploy

**Symptom (Luke: "this lock issue is MISERABLE. there needs to be a real
solution"):** after every `cortex-update.sh`, the next tool call returned
"GOVERNANCE LOCK REQUIRED" even though the lock file existed and was fresh.
This forced re-acquiring `begin_change` after every deploy, made the doctor
classify the current cycle as "leaked" (no lock), and cascaded into the
dogfood false-positive chain.

**Root cause — a timezone parse bug, not a designed purge:**

```bash
# BEFORE (buggy) — cortex-update.sh stale-lock cleanup, first pass:
_lock_heartbeat=$(python3 -c "...get('heartbeat_at','')[:19]")   # strips 'Z'!
_heartbeat_epoch=$(date -d "$_lock_heartbeat" +%s)               # parses as LOCAL
if [[ $(( _now - _heartbeat_epoch )) -gt 3600 ]]; then rm -f "$_lock"; fi
```

The heartbeat is ISO-8601 UTC ending in `Z` (e.g. `2026-08-05T08:42:54Z`).
`[:19]` slices off the `Z`, and `date -d` then interprets the marker-less
timestamp as LOCAL time. On a UTC+9 host (KST — Luke's fleet):

| heartbeat | date -d parse | computed age | verdict |
|---|---|---|---|
| `08:42:54Z` (FULL, with Z) | UTC → correct | **137s** (2 min) | fresh — KEPT |
| `08:42:54` (sliced [:19]) | parsed as +9h LOCAL | **32,537s** (9h) | stale — DELETED |

A 2-minute-old lock looked 9 hours old → exceeded the 3600s threshold →
deleted on EVERY deploy. The enforcer's `_has_governance_lock` (Python
`datetime.fromisoformat`, timezone-aware `now`) handled `Z` correctly the
whole time — the lock was being deleted under it by the deploy's own cleanup.

**Fix (commit f7f287e8):** keep the full heartbeat (with `Z`):
`date -d "2026-08-05T08:42:54Z" +%s` parses correctly. Verified: lock survived
deploy, only the current task's cycle remained PENDING, no leaked false
positives.

**General rule for ANY bash `date -d` on an ISO heartbeat: KEEP the `Z`**
(or use Python `fromisoformat`, which handles `Z`). When diagnosing a
"purged" lock, verify the age math FIRST — a fresh lock showing hours of age
is a TZ bug, not a real stale lock. Python purge paths (MCP server
`_is_lock_stale`, `purge-stale-governance-locks.py`) were already correct;
only the bash `date -d` path had the bug.

## Mandatory dogfood in the pre-push gate

**Luke: "make dogfood MANDATORY — I thought you did already."** The pre-push
hook (hermes-cortex repo + orchestrator host only) runs the FULL dogfood
cycle itself when the push touches any non-doc file:

```bash
# pre-push-pull, mandatory dogfood block
if [[ "$_REPO_TOP" == "$CORTEX_REPO_TOP" ]] && _detect_orch && [[ -n "$CHANGED_FILES" ]]; then
  _DOGFOOD_RELEVANT=0
  while IFS= read -r cf; do
    case "$cf" in
      *.md|docs/*|docs) : ;;              # docs exempt — nothing deployed changes
      *) _DOGFOOD_RELEVANT=1 ;;           # EVERYTHING else fires (inverted trigger)
    esac
  done <<< "$CHANGED_FILES"
  if [[ "$_DOGFOOD_RELEVANT" -eq 1 ]]; then
    bash "${HOME}/.hermes-cortex/scripts/cortex-dogfood.sh" --quiet ...
    [[ $_DOGFOOD_RC -ne 0 ]] && exit 1    # block the push on dogfood FAIL
  fi
fi
```

### Scope corrections (Luke, same day — three rounds)
1. "every script/enforcement file, INCLUDING changes in paths to these
   files... excepted would be docs" → **inverted trigger**: fire on any
   non-doc file, not a narrow pattern allowlist (a renamed script would have
   slipped past the list).
2. "and outside of hermes cortex... for non hc repos" → **WRONG reading by
   Esther**; Luke corrected: "dogfooding is really just REDEPLOYMENT of hc,
   so it's irrelevant to other repos" → **hermes-cortex repo ONLY**. A
   non-HC push redeploys nothing; it must never run the HC dogfood.
3. Keep the orchestrator-only scope from earlier.

### Own-task exemption (the dogfood false-positive chain)
The dogfood deploy reloads the enforcer plugin (and historically purged the
lock via the TZ bug), so after deploy the doctor sees THIS session's own
cycle with no active lock → classifies it as "leaked" → dogfood FAILs on
itself. Fix in `cortex-dogfood.sh`:

```bash
# Capture BEFORE deploy (deploy will purge/restart the lock state)
for _lf in "${HOME}/.hermes-cortex/state"/.governance-*.json; do
  [[ -f "$_lf" ]] || continue
  DOGFOOD_OWN_TASK=$(python3 -c "import json;print(json.load(open('$_lf')).get('task_id',''))" ...)
  [[ -n "$DOGFOOD_OWN_TASK" ]] && break
done
# In the verify step: subtract this task's cycles from the FAIL count
_OWN_CYCLES=$(echo "$DOCTOR_OUT" | grep -cE "❌.*${DOGFOOD_OWN_TASK}" || true)
_DOGFOOD_FAILS=$((_DOGFOOD_FAILS - _OWN_CYCLES))
```

Only THIS task's cycle is exempted — other leaked cycles still fail dogfood.

### Skill reloads are NOT lock-coupled
Luke asked whether the lock purge existed to force agents to reload skills.
Verification: `cortex-update.sh` has ZERO references to skills-loaded markers;
the enforcer never deletes them; the marker check is existence + exact content
(`session:<session_id>`), not a version comparison. The reload trigger is
deployed-skill drift → doctor's skill-drift check → agent re-`skill_view()`.
If the goal is "force skill reload on deploy," invalidate the per-session
marker (`state/skills-loaded/<session_id>`) — do NOT delete locks.

## Verification evidence (all done live)
- TZ age math: full-Z → 137s; sliced → 32,537s (the bug, reproduced).
- After fix: lock file survived `cortex-update.sh`; only current-task cycle
  PENDING; doctor clean.
- Mandatory dogfood: 7-case trigger matrix (HC script/rename/config fire;
  HC doc exempt; client-repo-a + client-web-app NEVER fire); RED test (drifted
  deployed state → dogfood FAIL rc=1); the gate ran on its own push
  (99f72be8, 1764f053, b5fb4872, f7f287e8).
