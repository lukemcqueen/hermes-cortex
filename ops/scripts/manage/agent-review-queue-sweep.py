#!/usr/bin/env python3
"""agent-review-queue-sweep.py - O5/G-5 review-queue stale-sweep + triage automation.

Measures the loop-governance unreviewed cycle backlog, auto-closes stale
STOP/auto-accepted cycles (decision STOP-check, unreviewed, older than the
age cutoff, clean outcome note), auto-cleans precommit test-fixture artifacts
(temp-repo commits scored into the PROD DB by the global hook — see
tests/conftest.py hermeticity contract), and surfaces everything else
(LOOP, MOVE ON, hard-fail STOP-x, PENDING) for human review. Never touches
overrides.

Safety contract (mirrors the MCP feedback_accept semantics):
  * only rows with user_overrode IS NULL are candidates
  * only the exact auto-accepted STOP-check decision qualifies
  * outcome notes containing fail/error/blocked/warn/escalat/issue/bug block
    auto-close
  * STOP-x (hard fail) and MOVE ON are surfaced, never closed
  * precommit test-fixture cleanup matches only the detached-HEAD / known
    test-repo task_id signatures (zero false positives on real commits) and
    marks them overridden (reversible), never deletes
  * reruns are idempotent: already-accepted rows are skipped

Exit protocol (no_agent cron watchdog pattern):
  * clean run, nothing notable -> no stdout, exit 0 (nothing delivered)
  * anomalies (PENDING leak older than 24h, hard-fail unreviewed older than
    7d) -> compact report on stdout, exit 1 (delivered as alert)

Evidence: every run appends one JSON line to the run log under the Hermes
Cortex state dir, and the latest totals are written to a state JSON.
"""

import argparse
import datetime
import glob
import json
import os
import sqlite3
import sys


def _state_dir():
    override = os.environ.get("REVIEW_STATE_DIR")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".hermes-cortex", "state")


def _db_file():
    override = os.environ.get("REVIEW_DB_PATH")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".hermes-cortex", "data", "loop-governance.db")


def _run_log():
    return os.path.join(_state_dir(), "review-queue-sweep.log")


def _state_json():
    return os.path.join(_state_dir(), "review-queue-sweep-state.json")


STOP_OK = "STOP \u2713"
NEGATIVE_MARKERS = (
    "fail", "error", "blocked", "warn", "escalat", "issue", "bug",
    "rollback", "regress", "stuck", "unresolved",
)

# Precommit test-fixture task_id signatures (slice 74f2ac46). The global git
# core.hookspath fires pre-commit-score on EVERY commit, including commits in
# temp/test repos; those rows land in the PROD loop-governance DB with
# task_id "precommit-<testrepo>-<branch>/<msg>". Two reliable signatures:
#   1. detached-HEAD: "-HEAD" (uppercase) in the task_id. Real commit-message
#      slugs are lowercased by the hook (tr '[:upper:]' '[:lower:]'), so
#      uppercase HEAD can only come from BRANCH=HEAD — the detached-HEAD state
#      pytest temp repos commit in. Zero false positives on real commits.
#   2. known test-repo names (master/feat-branch variants of the same repos).
_FIXTURE_KNOWN_PREFIXES = (
    "precommit-repo-", "precommit-commitme-", "precommit-dry-",
    "precommit-existing-", "precommit-idem-", "precommit-noagents-",
    "precommit-client-repo-", "precommit-enforcer-test-proj",
    "precommit-ext-repo-test", "precommit-hook-image-test",
    "precommit-tdd-gate-test", "precommit-test_",
    "precommit-hc-scope-test", "precommit-hooktest", "precommit-nonhc-test",
    "precommit-omz-sim-test", "precommit-project-repo-test",
    "precommit-sleak-test", "precommit-tdd-final", "precommit-tdd-no-infra",
    "precommit-hermes-cortex-private-",
)


def _is_fixture_task(task_id):
    """True when a loop_cycles task_id is a precommit test-fixture artifact."""
    if not task_id or not task_id.startswith("precommit-"):
        return False
    if "-HEAD" in task_id:
        return True
    return task_id.startswith(_FIXTURE_KNOWN_PREFIXES)


def _connect():
    con = sqlite3.connect(_db_file(), timeout=15)
    con.row_factory = sqlite3.Row
    return con


def _live_lock_task_ids():
    """Map live governance lock files to the session ids they protect."""
    live = set()
    pattern = os.path.join(_state_dir(), ".governance-*.json")
    for path in glob.glob(pattern):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            sid = data.get("session_id") or data.get("session")
            if sid:
                live.add(str(sid))
            base = os.path.basename(path)
            # fallback: lock filenames embed the session id after the prefix
            if base.startswith(".governance-"):
                live.add(base[len(".governance-"):].rsplit(".json", 1)[0])
        except Exception:
            continue
    return live


def _decision_bucket(decision):
    if decision is None:
        return "unknown"
    d = str(decision)
    if d.startswith(STOP_OK):
        return "stop_ok"
    if d.startswith("STOP"):
        return "stop_fail"
    if d.startswith("LOOP"):
        return "loop"
    if d.startswith("MOVE"):
        return "move_on"
    if d.startswith("PENDING"):
        return "pending"
    return "other"


def _note_is_clean(note):
    if not note:
        return True
    low = str(note).lower()
    return not any(m in low for m in NEGATIVE_MARKERS)


def measure(con, cutoff_ts):
    rows = con.execute(
        "SELECT id, task_id, decision, outcome_note, timestamp, session_id "
        "FROM loop_cycles WHERE user_overrode IS NULL ORDER BY id"
    ).fetchall()
    buckets = {}
    closable = []
    surfacing = []
    for r in rows:
        b = _decision_bucket(r["decision"])
        buckets[b] = buckets.get(b, 0) + 1
        if b == "stop_ok" and r["timestamp"] < cutoff_ts and _note_is_clean(r["outcome_note"]):
            closable.append(r)
        else:
            surfacing.append(r)
    return buckets, closable, surfacing


def close_cycles(con, closable, note):
    ids = [r["id"] for r in closable]
    if not ids:
        return 0
    con.executemany(
        "UPDATE loop_cycles SET user_overrode=0, outcome_note=? WHERE id=? AND user_overrode IS NULL",
        [(note, cid) for cid in ids],
    )
    con.commit()
    return con.total_changes


def clean_fixtures(con, note):
    """Mark precommit test-fixture cycles overridden (reversible).

    Safety net for temp/test-repo commits scored into the PROD DB by the
    global git hook (see tests/conftest.py hermeticity contract). Same
    contract as the rest of the sweep: only user_overrode IS NULL; idempotent
    (already-marked rows are skipped); never deletes — flipping user_overrode
    keeps history recoverable. Returns the list of marked ids.
    """
    rows = con.execute(
        "SELECT id, task_id FROM loop_cycles WHERE user_overrode IS NULL"
    ).fetchall()
    ids = [r["id"] for r in rows if _is_fixture_task(r["task_id"])]
    if not ids:
        return []
    con.executemany(
        "UPDATE loop_cycles SET user_overrode=1, decision=?, outcome_note=? "
        "WHERE id=? AND user_overrode IS NULL",
        [(STOP_OK, note, cid) for cid in ids],
    )
    con.commit()
    return ids


def check_alerts(con, surfacing, live_locks, pending_hours=24, hardfail_days=7):
    now = datetime.datetime.now()
    alerts = []
    for r in surfacing:
        b = _decision_bucket(r["decision"])
        try:
            ts = datetime.datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if b == "pending":
            sid = r["session_id"] or ""
            if sid and sid not in live_locks and (now - ts) > datetime.timedelta(hours=pending_hours):
                alerts.append("PENDING leak: cycle %d (%s) unscored %s, no live lock" % (r["id"], r["task_id"], r["timestamp"]))
        elif b == "stop_fail":
            if (now - ts) > datetime.timedelta(days=hardfail_days):
                alerts.append("hard-fail STOP unaddressed: cycle %d (%s) %s" % (r["id"], r["task_id"], r["timestamp"]))
    return alerts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=float, default=3.0, help="age cutoff in days (default 3)")
    ap.add_argument("--dry-run", action="store_true", help="report only, no writes")
    ap.add_argument("--report", action="store_true", help="always print summary")
    args = ap.parse_args()

    if not os.path.exists(_db_file()):
        print("review-queue-sweep: loop-governance DB not found; nothing to do")
        return 0

    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=args.days)
    cutoff_ts = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    con = _connect()
    try:
        # Precommit test-fixture safety net (never touches overrides).
        # Cleaned BEFORE measure so fixtures never enter the reported buckets.
        fixture_ids = sorted(
            r["id"] for r in con.execute(
                "SELECT id, task_id FROM loop_cycles WHERE user_overrode IS NULL"
            ).fetchall()
            if _is_fixture_task(r["task_id"])
        )
        fixture_note = (
            "auto-swept by agent-review-queue-sweep: precommit test-fixture "
            "artifact (temp-repo commit scored by the global git hook; "
            "test-DB isolation 74f2ac46); no real change"
        )

        buckets_before, closable, surfacing = measure(con, cutoff_ts)
        n_closable = len(closable)
        n_before = sum(buckets_before.values())
        note = (
            "auto-swept by agent-review-queue-sweep (O5/G-5): STOP auto-accepted, "
            "older than %.0fd, clean outcome note" % args.days
        )

        if args.dry_run:
            ids = sorted(r["id"] for r in closable)
            print("review-queue-sweep DRY-RUN: would close %d cycles (ids %s..%s)" % (
                n_closable, ids[0] if ids else "-", ids[-1] if ids else "-"))
            print("  would clean %d precommit test-fixture cycles (ids %s..%s)" % (
                len(fixture_ids), fixture_ids[0] if fixture_ids else "-",
                fixture_ids[-1] if fixture_ids else "-"))
            print("  unreviewed before: %d" % n_before)
            for k in ("stop_ok", "loop", "move_on", "stop_fail", "pending"):
                print("    %-10s %d" % (k, buckets_before.get(k, 0)))
            return 0

        if fixture_ids:
            con.executemany(
                "UPDATE loop_cycles SET user_overrode=1, decision=?, outcome_note=? "
                "WHERE id=? AND user_overrode IS NULL",
                [(STOP_OK, fixture_note, cid) for cid in fixture_ids],
            )
            con.commit()

        n_closed = close_cycles(con, closable, note)

        buckets_after, _, surfacing_after = measure(con, cutoff_ts)
        n_after = sum(buckets_after.values())

        alerts = check_alerts(con, surfacing, _live_lock_task_ids())

        # Alert dedup: deliver each anomaly once (state-tracked seen set),
        # otherwise the daily cron spams the same backlog every tick.
        prev_state = {}
        if os.path.exists(_state_json()):
            try:
                with open(_state_json(), "r", encoding="utf-8") as fh:
                    prev_state = json.load(fh)
            except Exception:
                prev_state = {}
        seen = set(prev_state.get("seen_alerts", []))
        if prev_state.get("last_run", {}).get("alerts"):
            seen.update(prev_state["last_run"]["alerts"])
        new_alerts = [a for a in alerts if a not in seen]
        seen.update(new_alerts)

        record = {
            "ts": now.strftime("%Y-%m-%d %H:%M:%S"),
            "dry_run": False,
            "days": args.days,
            "before_total": n_before,
            "closed": n_closed,
            "fixture_cleaned": len(fixture_ids),
            "fixture_ids": fixture_ids,
            "after_total": n_after,
            "buckets_before": buckets_before,
            "buckets_after": buckets_after,
            "alerts": alerts,
            "new_alerts": new_alerts,
        }
        os.makedirs(_state_dir(), exist_ok=True)
        with open(_run_log(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        with open(_state_json(), "w", encoding="utf-8") as fh:
            json.dump({"last_run": record, "seen_alerts": sorted(seen)}, fh, indent=1)

        if args.report or new_alerts:
            lines = []
            lines.append("review-queue-sweep: closed %d/%d unreviewed (%d remain)" % (n_closed, n_before, n_after))
            if fixture_ids:
                lines.append("  fixtures: cleaned %d precommit test-fixture cycles (test-repo commits)" % len(fixture_ids))
            for k in ("stop_ok", "loop", "move_on", "stop_fail", "pending"):
                lines.append("  %-10s %d" % (k, buckets_after.get(k, 0)))
            for a in new_alerts:
                lines.append("  ALERT: " + a)
            print("\n".join(lines))
            return 1 if new_alerts else 0
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
