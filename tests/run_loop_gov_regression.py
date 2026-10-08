#!/usr/bin/env python3
"""Runnable generator for the loop-governance regression claim.

Re-executes the loop-governance / reviewer test set against the CURRENT
revision, records the revision it ran against, and writes the full transcript
to tests/artifacts/loop-gov-regression.txt. Exits non-zero if ANY test or the
static gate fails, so the artifact cannot be a stale green.

Why this exists: a prose summary of test results is not evidence a later
reviewer can re-run (adversarial finding ADV-10715-1). One command must
reproduce the measurement.

Usage:  python3 tests/run_loop_gov_regression.py
"""
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ARTIFACT = REPO / "tests" / "artifacts" / "loop-gov-regression.txt"

_HOME = str(Path.home())
_REPO = str(REPO)
_PY_BIN = str(Path(sys.executable).parent)


def _scrub(text: str) -> str:
    """Rule 16: this artifact is committed to a PUBLIC repo, so the host's
    home path, the checkout path and the interpreter's bin dir are replaced
    with placeholders. Reproducing the artifact must not republish them."""
    return (text.replace(_REPO, "<repo>")
                .replace(_HOME, "~")
                .replace(_PY_BIN, "<python-bin>"))

# Every test asserted in the change's evidence note. Scope of the artifact must
# equal the scope of the claim.
TESTS = [
    "tests/test_loop_gov_mcp_nonblocking.py",
    "tests/test_loop_gov_review_repo.py",
    "tests/test_loop_gov_multi_session.py",
    "tests/test_loop_gov_stale_purge.py",
    "tests/test_loop_gov_db_lock_recovery.py",
    "tests/test_loop_gov_review_leak.py",
    "tests/test_orphan_cycle_resolution.py",
    "tests/test_reviewer_backends.py",
    "tests/test_review_independence.py",
    "tests/test_review_material_bound.py",
    "tests/test_review_material_scope.py",
    "tests/test_review_material_consistency.py",
    "tests/test_manifest_generator_interpreter.py",
    "tests/test_refused_close_visible.py",
    "tests/test_loop_gov_lock_watchdog.py",
    "tests/test_loop_gov_mcp_startup.py",
    # The two guards added for the always-review receipt gate and skill parity. Both
    # were OUTSIDE this set: test_verify_landed.py had no __main__ runner (so running it
    # executed nothing and exited 0 — a vacuous PASS, the class the guard at line 122
    # rejects), and the parity check that measures skill drift was never exercised here
    # at all. A guard the harness does not run is a guard nobody notices has rotted.
    "tests/test_verify_landed.py",
    "tests/test_skill_drift_parity.py",
]

GATE_FILE = "mcp-servers/loop-gov-mcp.py"
GATE_LEVEL = "A4"


def _run(argv, cwd=REPO, timeout=300):
    return subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def _git(*args) -> str:
    return _run(["git", *args]).stdout.strip()


def _tail(text: str, n: int = 60) -> str:
    """Last n non-blank lines.

    Generous on purpose: these harness scripts print a `PASS (N):` summary
    followed by one line per test, and a short tail used to cut most of those
    names out of the artifact — which made a true claim look contradicted by
    its own evidence. The full summary must survive.
    """
    lines = [ln for ln in text.rstrip().splitlines() if ln.strip()]
    return "\n".join(lines[-n:])


def _gate(path: str) -> tuple:
    """Run the static gate on `path`; return (ok, summary_lines)."""
    proc = _run([sys.executable, "ops/scripts/quality/adversarial-verify.py",
                 "--file", path, "--level", GATE_LEVEL, "--gate"], timeout=600)
    lines = [ln.strip() for ln in proc.stdout.splitlines()
             if "Summary:" in ln or "Medium:" in ln or "Low:" in ln
             or "critical" in ln or "GATE_" in ln]
    return proc.returncode == 0, lines


def main() -> int:
    revision = _git("rev-parse", "--short", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    out = []
    failures = []

    out.append("loop-governance regression artifact")
    out.append("=" * 72)
    out.append(f"generated      : {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    out.append(f"revision       : {revision}  (branch {branch})")
    out.append(f"interpreter    : Python {sys.version.split()[0]} (<python-bin>/python3)")
    out.append(f"generator      : tests/run_loop_gov_regression.py")
    out.append("")
    out.append("Re-run with:  python3 tests/run_loop_gov_regression.py")
    out.append("")

    # ── 1. The test set ──
    out.append("-" * 72)
    out.append(f"TEST SET ({len(TESTS)} files)")
    out.append("-" * 72)
    for rel in TESTS:
        path = REPO / rel
        if not path.is_file():
            failures.append(f"{rel}: MISSING")
            out.append(f"[FAIL] {rel} -- file does not exist")
            continue
        # A test file with no __main__ runner imports and exits 0 having executed
        # NOTHING (pytest is not installed on this host), so the harness would record a
        # vacuous PASS. Found on test_review_material_scope.py, 2026-10-08 (cycle 10916).
        if "__main__" not in path.read_text(errors="ignore"):
            failures.append(f"{rel}: no __main__ runner (vacuous PASS)")
            out.append(f"[FAIL] {rel} -- no __main__ runner: exits 0 without running a test")
            continue
        proc = _run([sys.executable, rel])
        ok = proc.returncode == 0
        if not ok:
            failures.append(f"{rel}: rc={proc.returncode}")
        out.append(f"[{'PASS' if ok else 'FAIL'}] {rel}  rc={proc.returncode}")
        # Record EVERY check's outcome, not just the tail. A tail-only artifact
        # left an individual check's result uncommitted whenever its file printed
        # more than 60 lines afterwards, so a claim about it had no committed
        # evidence to cite -- the reviewer had to report it as unverified, three
        # cycles running (2026-10-08). Failures and outcomes are the part that must
        # always survive truncation.
        combined = proc.stdout + proc.stderr
        keep = [ln for ln in combined.splitlines()
                if re.search(r"^\s*(PASS|FAIL)\b|ALL PASS|RESULT:|^PASS \(", ln)]
        rows = []
        for ln in [*keep, *_tail(combined).splitlines()]:
            if ln.strip() and ln not in rows:
                rows.append(ln)
        for ln in rows:
            out.append(f"        {ln}")
        out.append("")

    # ── 2. Static gate, current revision ──
    out.append("-" * 72)
    out.append(f"STATIC GATE  {GATE_FILE}  level {GATE_LEVEL}")
    out.append("-" * 72)
    ok_now, lines_now = _gate(GATE_FILE)
    if not ok_now:
        failures.append(f"static gate on {GATE_FILE}: FAILED")
    out.append(f"[{'PASS' if ok_now else 'FAIL'}] interim/working revision {revision}")
    for ln in lines_now:
        out.append(f"        {ln}")
    out.append("")

    # ── 3. Same gate on the PRE-FIX revision, so "adds no findings" is checkable ──
    with tempfile.TemporaryDirectory(prefix="loop-gov-prev-") as tmp:
        prev_file = Path(tmp) / "loop-gov-mcp.prev.py"
        prev_file.write_text(_git("show", "HEAD~1:" + GATE_FILE))
        ok_prev, lines_prev = _gate(str(prev_file))
    out.append(f"[{'PASS' if ok_prev else 'FAIL'}] PRE-FIX revision HEAD~1 ({_git('rev-parse', '--short', 'HEAD~1')})")
    for ln in lines_prev:
        out.append(f"        {ln}")
    out.append("")
    out.append("Comparison: the two summaries above must agree on their finding")
    out.append("counts (same total / medium / low / info), which is the claim that")
    out.append("this change introduces no new static findings.")
    out.append("")

    out.append("=" * 72)
    out.append(f"RESULT: {'ALL PASS' if not failures else 'FAILURES: ' + '; '.join(failures)}")
    out.append("=" * 72)

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text("\n".join(_scrub(ln) for ln in out) + "\n")

    print(f"artifact: {ARTIFACT}")
    print(f"revision: {revision}   tests: {len(TESTS)}")
    if failures:
        print("RESULT: FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("RESULT: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
