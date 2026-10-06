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
    "tests/test_refused_close_visible.py",
    "tests/test_loop_gov_lock_watchdog.py",
    "tests/test_loop_gov_mcp_startup.py",
]

GATE_FILE = "mcp-servers/loop-gov-mcp.py"
GATE_LEVEL = "A4"


def _run(argv, cwd=REPO, timeout=300):
    return subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def _git(*args) -> str:
    return _run(["git", *args]).stdout.strip()


def _tail(text: str, n: int = 8) -> str:
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
        proc = _run([sys.executable, rel])
        ok = proc.returncode == 0
        if not ok:
            failures.append(f"{rel}: rc={proc.returncode}")
        out.append(f"[{'PASS' if ok else 'FAIL'}] {rel}  rc={proc.returncode}")
        for ln in _tail(proc.stdout + proc.stderr).splitlines():
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
