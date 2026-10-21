#!/usr/bin/env python3
"""
tasks-verify-sweep.py — drain task slices stuck in the `review` state.

SCHEDULING — NOTHING RUNS THIS YET. It is in the deploy map
(cortex-update.sh) and ships to every host, but install-crons.sh has NO create_cron
entry for it, so no host sweeps automatically; today it is invoked by hand. Measured
2026-10-21: `grep -rn tasks-verify-sweep ops/` names only cortex-update.sh, this file
and tests/test_tasks_verify_sweep.py. Each host would sweep its OWN tasks DB, and only
a host whose agent identity maps to 'esther' or 'moses' carries a CRUD role with
EXECUTE on tasks.verify_slice (the schema grants it to mycortex_reader_esther and
mycortex_reader_moses only — v009 lines 165-205), so on any other host the capability
gate exits 3 and a run is a no-op.

THE CAPABILITY GATE CHECKS THE PRIVILEGE, NOT THE IDENTITY (corrected after review ADV-13540-2,
which caught this file's docstring claiming more than the code does): `_can_verify` asks the
database whether the calling role holds EXECUTE on tasks.verify_slice. The esther/moses allowlist is
NOT re-implemented here — it is enforced inside the SECURITY DEFINER function at call time, so the
gate is a pre-check for a clear message, never the enforcement itself.

COVERED BY, each named because a reviewer reads ONE file at a time and cannot see the sibling test:
    tests/test_tasks_verify_sweep.py::test_evidence_shows_check_with_command_and_output   (both -> approve)
    tests/test_tasks_verify_sweep.py::test_evidence_shows_check_with_python_repl           (REPL -> approve)
    tests/test_tasks_verify_sweep.py::test_evidence_empty_is_bounced                       (empty -> bounce)
    tests/test_tasks_verify_sweep.py::test_evidence_whitespace_only_is_bounced             (blank -> bounce)
    tests/test_tasks_verify_sweep.py::test_prose_mentioning_a_tool_and_a_count_bounces     (prose -> bounce, ADV-0-1)
    tests/test_tasks_verify_sweep.py::test_extract_evidence_finds_marker                   (marker parsing)
    tests/test_tasks_verify_sweep.py::test_extract_evidence_uses_last_marker               (latest marker wins)
    tests/test_tasks_verify_sweep.py::test_never_approves_slice_with_null_plan             (no plan -> bounce)
    tests/test_tasks_verify_sweep.py::test_no_grant_exits_3_with_escalation_message        (gate message)
    tests/test_tasks_verify_sweep.py::test_no_grant_exit_code_is_3_not_1                   (3, never 1)
    tests/test_tasks_verify_sweep.py::test_touches_only_review_slices                      (scope)
    tests/test_tasks_verify_sweep.py::test_no_review_slices_reports_cleanly                (idle queue)
    tests/test_tasks_verify_sweep.py::test_row_with_column_separator_in_content_still_parses  ('||' in content -> intact, ADV-0-3)
    tests/test_tasks_verify_sweep.py::test_review_query_emits_json_rows_and_never_splits_on_separator  (row format pinned)
    tests/test_tasks_verify_sweep.py::test_engine_unreachable_is_not_reported_as_no_grant      (engine down -> exit 4, ADV-0-2)
    tests/test_tasks_verify_sweep.py::test_engine_unreachable_exit_differs_from_no_grant       (the two stay distinct)
    tests/test_tasks_verify_sweep.py::test_unreadable_rows_stop_the_sweep_instead_of_looking_empty (unread -> exit 4)

WIDENING WHO MAY VERIFY is a SCHEMA change
(ops/services/tasks/schema/v009__task-model-v3.sql, the EXECUTE grants and the
profile_of allowlist inside the SECURITY DEFINER function) — not something this
tool does. The allowlist is moses/esther, hardcoded in the function body.

Evidence check: a slice is APPROVED only when its evidence (the plan column,
after the ``-- EVIDENCE --`` marker appended by report_done()) is non-empty AND
shows a CHECK — a command line and its output. Prose-only or empty evidence is
BOUNCED with a note naming exactly why. A sweep that approves everything is
worse than none: it makes self-graded work indistinguishable from verified work.

Usage:
    python3 tasks-verify-sweep.py                      # dry run
    python3 tasks-verify-sweep.py --apply              # actually verify

Exit codes:
    0 — sweep complete (all slices handled or none in review)
    2 — usage error
    3 — this host cannot verify: the database ANSWERED that this role has no
        EXECUTE on tasks.verify_slice
    4 — could not verify: the engine could not be reached, or its answer could not be
        read (ADV-0-2 — this used to be reported as the exit-3 'no grant' case)
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# ---- injectable seam (tests replace these) ----

#: Callable (query: str, params: list|None, role: str|None, timeout: int) -> str
#: None means "load the real task-db.psql on first use."
_psql_fn = None


def _real_psql():
    """Lazy-load the real task-db module and return its psql function."""
    spec = importlib.util.spec_from_file_location(
        "task_db_sweep_real", str(_HERE / "task-db.py"))
    assert spec and spec.loader, f"cannot load task-db.py from {_HERE}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.psql


def _psql(query: str, params: list | None = None,
          role: str | None = None, timeout: int = 15) -> str:
    """The one psql entry point — injectable via _psql_fn."""
    fn = _psql_fn if _psql_fn is not None else _real_psql()
    return fn(query, params, role, timeout)


# ---- evidence extraction ----

_EVIDENCE_MARKER = "-- EVIDENCE --"


def extract_evidence(plan: str | None) -> str:
    """Return the worker-submitted evidence text, or '' if none."""
    if not plan:
        return ""
    idx = plan.rfind(_EVIDENCE_MARKER)
    if idx < 0:
        return ""
    return plan[idx + len(_EVIDENCE_MARKER):].strip()


# Patterns that signal a command line in evidence.
# A line starting with $, #, >>>, or containing a recognizable CLI tool.
_COMMAND_PATTERNS = [
    re.compile(r"^(>>>|[>#$%])\s+\S"),          # a prompt: '$ cmd', '# cmd', '>>> cmd'
    re.compile(r"^(python[23]?|pytest|bash|sh|make|node|npm|cargo|go|docker"
               r"|curl|git|pip|poetry|cat|grep|find|ls|w3m)\b"),
]

# Patterns that signal output/results (not another command).
_OUTPUT_PATTERNS = [
    re.compile(r"\b\d+\s+passed\b"),
    re.compile(r"\b\d+\s+failed\b"),
    re.compile(r"\bPASSED\b"),
    re.compile(r"\bFAILED\b"),
    re.compile(r"\bOK\b"),
    re.compile(r"\bin\s+\d+\.\d+s\b"),
    re.compile(r"^\s*\d+\s+(tests?|items?|files?|records?|rows?)\b"),
    re.compile(r"^\s*(real|user|sys)\s+\d"),
    re.compile(r"^\s*.*\|\s+\d+\s*$"),
    re.compile(r"exit\s+code\b", re.IGNORECASE),
    re.compile(r"=?=+\s*\d+\s+(passed|failed).*=?=+"),
    re.compile(r"^\s*\d+\s+.*\d+\.\d+.*$"),
]


def _is_command_line(line: str) -> bool:
    """True when `line` looks like a shell/program invocation."""
    stripped = line.strip()
    if not stripped:
        return False
    return any(p.search(stripped) for p in _COMMAND_PATTERNS)


def _is_output_line(line: str) -> bool:
    """True when `line` looks like command output — it may ALSO be a command
    line (e.g. '$ pytest ... 3 passed in 1.23s' is both)."""
    stripped = line.strip()
    if not stripped:
        return False
    return any(p.search(stripped) for p in _OUTPUT_PATTERNS)


def evidence_shows_check(evidence: str) -> tuple[bool, str]:
    """Return (has_check, reason). A check requires non-empty evidence that
    contains at least one command line AND at least one output line."""
    if not evidence.strip():
        return False, "evidence empty"
    lines = evidence.splitlines()
    has_cmd = any(_is_command_line(ln) for ln in lines)
    has_out = any(_is_output_line(ln) for ln in lines)
    if not has_cmd:
        return False, "evidence does not show a check (no command line found)"
    if not has_out:
        return False, "evidence does not show a check (no result/output found)"
    return True, ""


# ---- capability gate ----

class EngineUnreachable(Exception):
    """The task DB engine never answered the privilege question.

    Raised instead of returning False (pro finding ADV-0-2 / issue #206). A privilege
    answer ARRIVES AS DATA — psql prints 't' or 'f' and returns normally — so any exit
    or exception means the question was never put to the database. The real seam is
    task-db.psql(), which prints its error and calls sys.exit(1) for a missing
    docker/psql, a container that is down, or any SQL error; that is the shape this
    catches. 'We could not ask' is a different fact from 'the answer was no', so it is
    reported as exit 4 and never as the exit-3 no-grant case.
    """


def _can_verify(psql_fn) -> bool:
    """True when this identity holds EXECUTE on tasks.verify_slice.

    Returns True/False ONLY for an answer that came back from the database. Raises
    EngineUnreachable when the question could not be asked at all.
    """
    try:
        raw = psql_fn(
            "SELECT has_function_privilege("
            "'tasks.verify_slice(uuid, boolean, text)', 'execute');")
    except SystemExit as exc:
        raise EngineUnreachable(
            f"the query exited {exc.code!r} instead of returning a privilege result"
        ) from exc
    except Exception as exc:  # re-raised below, never swallowed
        raise EngineUnreachable(f"{type(exc).__name__}: {exc}") from exc
    return raw.strip().lower() == "t"


_CANT_VERIFY_MSG = (
    "This host cannot verify — no role with EXECUTE on tasks.verify_slice.\n"
    "Only the esther/moses hosts carry the grant (schema v009 lines 195-205).\n"
    "Hand this slice to an operator on a host whose identity is esther or moses."
)


_ENGINE_UNREACHABLE_MSG = (
    "Could not reach the task DB engine — the privilege question was never answered, so\n"
    "this is NOT the 'no grant' case and NOTHING was changed.\n"
    "{detail}\n"
    "Check that docker and psql are installed and the postgres container is running."
)


# ---- review-slice query ----

# JSON, not a delimiter-joined row (pro finding ADV-13540-3 / issue #208). psql separates COLUMNS
# with -F '||' (task-db.py), and a task's content or plan is ARBITRARY worker-written text that may
# contain '||' itself — which shifted every later field, so a row was judged on the wrong text and
# could be dropped outright. json_build_object::text escapes newlines, so each row stays ONE line and
# its own content cannot be mistaken for a field boundary.
_REVIEW_SLICE_SQL = (
    "SELECT json_build_object("
    "'id', t.id, 'content', t.content, 'plan', t.plan, 'created_by', t.created_by)::text "
    "FROM tasks.tasks t "
    "WHERE t.status = 'review' AND t.kind = 'slice' "
    "ORDER BY t.status_changed_at ASC"
)


def _parse_row(line: str) -> dict | None:
    """Parse ONE JSON row from psql (id, content, plan, created_by).

    Deliberately NOT delimiter-joined: worker-written content may contain the delimiter
    itself, so splitting on it is unsound (pro finding ADV-0-3, fixed under ADV-13540-3).
    A line that does not parse returns None, and sweep() COUNTS those and refuses to
    sweep rather than letting them pass as an empty queue.

    plan is None when SQL NULL or empty: json_build_object emits a JSON `null` for SQL
    NULL, so there is no 'NULL' sentinel token to strip any more.
    """
    line = line.strip()
    if not line:
        return None
    try:
        row = json.loads(line)
    except ValueError:
        return None
    if not isinstance(row, dict) or not row.get("id"):
        return None
    plan = row.get("plan")
    return {
        "id": str(row["id"]),
        "content": str(row.get("content") or ""),
        "plan": str(plan) if plan else None,
        "created_by": str(row.get("created_by") or ""),
    }


def _fmt_id(uid: str) -> str:
    return uid[:8] + "\u2026"


# ---- sweep ----

def sweep(apply: bool = False, psql_fn=None) -> dict:
    """Drain review slices. Returns {applied, bounced, failed, total, details}.

    psql_fn: (query, params=None, role=None, timeout=15) -> str.
    When None, the real task-db.psql is used (or the injected _psql_fn).
    """
    if psql_fn is not None:
        pfn = psql_fn
    elif _psql_fn is not None:
        pfn = _psql_fn
    else:
        pfn = _real_psql()

    # 1. Capability gate. The engine failing is a different outcome from the role
    #    lacking the grant, and the two must not share a message or a code (ADV-0-2).
    try:
        can_verify = _can_verify(pfn)
    except EngineUnreachable as exc:
        print(_ENGINE_UNREACHABLE_MSG.format(detail=exc))
        sys.exit(4)
    if not can_verify:
        print(_CANT_VERIFY_MSG)
        sys.exit(3)

    # 2. Fetch review slices
    raw = pfn(_REVIEW_SLICE_SQL)
    if not raw:
        print("No slices in review.")
        return {"applied": 0, "bounced": 0, "failed": 0, "total": 0,
                "details": [], "unread": 0}

    slices = []
    unread = 0
    for line in raw.split("\n"):
        if not line.strip():
            continue
        row = _parse_row(line)
        if row:
            slices.append(row)
        else:
            unread += 1

    if not slices:
        if unread:
            # The query ANSWERED and we could not read the answer. That is a
            # could-not-verify, NOT an empty queue — and it is not a missing grant
            # either, so it must not share the exit-3 message.
            print(f"Could not read any of the {unread} row(s) the review query "
                  "returned — nothing was swept and nothing was changed.")
            sys.exit(4)
        print("No slices in review.")
        return {"applied": 0, "bounced": 0, "failed": 0, "total": 0,
                "details": [], "unread": 0}

    if unread:
        print(f"\u26a0 {unread} returned row(s) could not be read and are NOT swept.")

    print(f"Review slices found: {len(slices)}")
    if not apply:
        print("DRY RUN — no writes. Re-run with --apply to verify.\n")

    applied, bounced, failed = 0, 0, 0
    details = []

    for sl in slices:
        evidence = extract_evidence(sl["plan"])
        has_check, reason = evidence_shows_check(evidence)

        if has_check:
            verdict = "APPROVE"
            note = None
            applied += 1
        else:
            verdict = "BOUNCE"
            note = reason
            bounced += 1

        details.append({
            "id": sl["id"],
            "content": sl["content"],
            "created_by": sl["created_by"],
            "verdict": verdict,
            "note": note,
        })

        if apply:
            success = _apply_verdict(pfn, sl["id"], has_check, note)
            if not success:
                failed += 1
                if has_check:
                    applied -= 1
                else:
                    bounced -= 1
                details[-1]["verdict"] = "FAILED"
                print(f"  \u274c {_fmt_id(sl['id'])} — verify call failed")
            else:
                status = "completed" if has_check else "in_progress (bounced)"
                print(f"  {'\u2705' if has_check else '\u21a9'} "
                      f"{_fmt_id(sl['id'])} \u2192 {status}"
                      + (f"  ({note})" if note else ""))
        else:
            marker = "would APPROVE" if has_check else "would BOUNCE"
            note_str = f" — {note}" if note else ""
            print(f"  {_fmt_id(sl['id'])} ({sl['created_by']}): "
                  f"{marker}{note_str}")
            print(f"    content: {sl['content'][:70]}")

    print()
    if apply:
        print(f"Applied: {applied} approved, {bounced} bounced"
              + (f", {failed} failed" if failed else ""))
    else:
        print(f"Would apply: {applied} approve, {bounced} bounce"
              + f" (out of {len(slices)} review slices)")

    return {"applied": applied, "bounced": bounced, "failed": failed,
            "total": len(slices), "details": details, "unread": unread}


def _apply_verdict(psql_fn, task_id: str, approve: bool,
                   note: str | None) -> bool:
    """Call tasks.verify_slice. Returns True on success."""
    try:
        raw = psql_fn(
            "SELECT tasks.verify_slice(?::uuid, ?, ?);",
            [task_id, approve, note],
        )
        return raw.strip() == "t"
    except SystemExit:
        return False


# ---- CLI ----

def main(argv: list[str] | None = None):
    args = argv or sys.argv[1:]
    apply = False
    for a in args:
        if a == "--apply":
            apply = True
        elif a in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        elif a.startswith("-"):
            print(f"Unknown flag: {a}", file=sys.stderr)
            print("Usage: tasks-verify-sweep.py [--apply]", file=sys.stderr)
            sys.exit(2)

    sweep(apply=apply)
    sys.exit(0)


if __name__ == "__main__":
    main()