#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# governance-refused-close-advisory.sh — warn at the moment work is STACKED.
#
# Called by the pre-commit hook. If this repo's active governance lock carries a
# `close_refused` marker (written by the gate when the adversarial review refused
# the close), committing now stacks a second change under that lock: the reviewer
# will later read a task description that no longer matches the diff, which the
# close-out skill calls unclosable by a worker (cycle 10445, 2026-10-02).
#
# ADVISORY ONLY — always exits 0. Blocking here could deadlock an agent whose close
# is legitimately stuck, which is worse than the fault it prevents. The review that
# refused the close is unchanged; this only makes the state visible in time.
#
# Usage:  governance-refused-close-advisory.sh [repo_slug]
#         (repo_slug defaults to the current git repo's directory name)
# Env:    GOVERNANCE_STATE_DIR overrides ~/.hermes-cortex/state (tests use this).
# ─────────────────────────────────────────────────────────────
set -u

STATE_DIR="${GOVERNANCE_STATE_DIR:-$HOME/.hermes-cortex/state}"
REPO_SLUG="${1:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || echo generic)" 2>/dev/null || echo generic)}"

[[ -d "$STATE_DIR" ]] || exit 0

for lock_file in "$STATE_DIR"/.governance-*.json; do
  [[ -f "$lock_file" ]] || continue
  REFUSED=$(REPO_SLUG="$REPO_SLUG" LOCK_FILE="$lock_file" python3 - <<'PY' 2>/dev/null
import json, os
try:
    with open(os.environ["LOCK_FILE"]) as fh:
        d = json.load(fh)
except Exception:
    raise SystemExit(0)
slug = d.get("repo_slug") or os.environ["REPO_SLUG"]
if slug != os.environ["REPO_SLUG"]:
    raise SystemExit(0)
r = d.get("close_refused")
if not r:
    raise SystemExit(0)
ids = ",".join(str(x) for x in (r.get("finding_ids") or [])[:4])
print("|".join([str(r.get("cycle_id", "?")), str(r.get("verdict", "?")),
                str(r.get("blocking", "?")), ids, str(r.get("at", "?"))]))
PY
)
  [[ -n "$REFUSED" ]] || continue
  IFS='|' read -r _cid _verdict _blocking _ids _at <<< "$REFUSED"
  echo ""
  echo "⚠️  ADVISORY — your close for cycle ${_cid} was REFUSED by the review"
  echo "    (${_verdict}, ${_blocking} blocking finding(s): ${_ids}; refused at ${_at})."
  echo "    The lock is still held, so what you commit now is STACKED under it: the"
  echo "    reviewer will later read a description that no longer matches the diff,"
  echo "    which is unclosable by a worker. Legitimate exits:"
  echo "      1. fix the findings, then rereview_change with a NEW note (not end_change)"
  echo "      2. or ask an orchestrator to clear the cycle (it is already scored)"
  echo "    Nothing is blocked by this message."
  echo ""
  break
done

exit 0
