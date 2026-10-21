#!/usr/bin/env python3
"""
tasks-verify-sweep.py — drain task slices stuck in the `review` state.

HOW IT GETS SCHEDULED: a per-host cron runs this periodically. Only hosts whose
agent identity maps to 'esther' or 'moses' carry a CRUD role with EXECUTE on
tasks.verify_slice (the schema grants it to mycortex_reader_esther and
mycortex_reader_moses only — v009 lines 165-205), so on any other host the
capability gate exits 3 and the cron is a no-op.

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
    3 — this host cannot verify (no EXECUTE on tasks.verify_slice)
"""

from __future__ import annotations

import importlib.util
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
    re.compile(r"^\s*[\$#]\s+"),                # shell prompt
    re.compile(r"^\s*>>>\s"),                   # Python REPL
    re.compile(r"\bpython[23]?[\s\-]"),         # python, python3 -m
    re.compile(r"\bpytest\b"),                  # pytest
    re.compile(r"\bgo\s+test\b"),               # go test
    re.compile(r"\bcargo\s+(test|run|build)\b"),
    re.compile(r"\bmake\b"),
    re.compile(r"\bnpm\s+(test|run)\b"),
    re.compile(r"\bnode\s"),
    re.compile(r"\bbash\s"),
    re.compile(r"\bsh\s"),
    re.compile(r"\bcurl\b"),
    re.compile(r"\bgit\s+(diff|log|status)\b"),
    re.compile(r"\bdocker\s"),
    re.compile(r"\bpoetry\s+run\b"),
    re.compile(r"\bpip\s+(install|list|show)\b"),
    re.compile(r"\bcat\s"),
    re.compile(r"\bgrep\b"),
    re.compile(r"\bfind\s"),
    re.compile(r"\bls\s"),
    re.compile(r"\bw3m\b"),
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

def _can_verify(psql_fn) -> bool:
    """True when this identity holds EXECUTE on tasks.verify_slice."""
    try:
        raw = psql_fn(
            "SELECT has_function_privilege("
            "'tasks.verify_slice(uuid, boolean, text)', 'execute');")
        return raw.strip().lower() == "t"
    except SystemExit:
        return False


_CANT_VERIFY_MSG = (
    "This host cannot verify — no role with EXECUTE on tasks.verify_slice.\n"
    "Only the esther/moses hosts carry the grant (schema v009 lines 195-205).\n"
    "Hand this slice to an operator on a host whose identity is esther or moses."
)


# ---- review-slice query ----

_REVIEW_SLICE_SQL = (
    "SELECT t.id, "
    "regexp_replace(t.content, E'[\\\\n\\\\r]', ' ', 'g') AS content, "
    "regexp_replace(t.plan, E'[\\\\n\\\\r]', ' ', 'g') AS plan, "
    "t.created_by "
    "FROM tasks.tasks t "
    "WHERE t.status = 'review' AND t.kind = 'slice' "
    "ORDER BY t.status_changed_at ASC"
)


def _parse_row(line: str) -> dict | None:
    """Parse a ||-delimited row from psql (id, content, plan, created_by)."""
    parts = [p.strip() for p in line.split("||")]
    if len(parts) < 4:
        return None
    return {
        "id": parts[0],
        "content": parts[1],
        "plan": parts[2] if parts[2] and parts[2] != "NULL" else None,
        "created_by": parts[3],
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

    # 1. Capability gate
    if not _can_verify(pfn):
        print(_CANT_VERIFY_MSG)
        sys.exit(3)

    # 2. Fetch review slices
    raw = pfn(_REVIEW_SLICE_SQL)
    if not raw:
        print("No slices in review.")
        return {"applied": 0, "bounced": 0, "failed": 0, "total": 0,
                "details": []}

    slices = []
    for line in raw.split("\n"):
        row = _parse_row(line)
        if row:
            slices.append(row)

    if not slices:
        print("No slices in review.")
        return {"applied": 0, "bounced": 0, "failed": 0, "total": 0,
                "details": []}

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
            "total": len(slices), "details": details}


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