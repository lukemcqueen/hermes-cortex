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
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ARTIFACT = REPO / "tests" / "artifacts" / "loop-gov-regression.txt"

# pytest is NOT installed for the interpreter this harness runs under, so a pytest-style file used to
# be indistinguishable from a FAILURE. The interpreter is resolved BY CAPABILITY through the resolver
# every deployed script already uses (`ops/scripts/lib/python-with-module.sh`) — never from a
# hardcoded venv path. A path this repo does not create (measured: $HOME/.hermes/tools/pytest-venv,
# built by hand on one host) resolves on exactly that host and degrades silently everywhere else,
# where every pytest-style file then reports NOT RUN — which reads as a clean run to anyone who
# reads only the summary (adversarial finding ADV-13116-1, 2026-10-18).
#
# So the no-pytest case is not a silent downgrade: it names the create step that is ITSELF
# committed. `ops/scripts/lib/ensure-pytest.sh` is that step — idempotent, verified by import, and
# age-gated through `ops/scripts/health/check-package-age.py` — and it installs the declared set in
# `ops/install/requirements.txt` (pytest is declared there) into the fleet venv, which is the venv
# cortex-update.sh registers every MCP server against. The resolver knows about every other capable
# interpreter on the host.
RESOLVER = REPO / "ops" / "scripts" / "lib" / "python-with-module.sh"
ENSURE_PYTEST = "ops/scripts/lib/ensure-pytest.sh"
NO_PYTEST_HINT = (
    "no interpreter can import pytest — create one with: "
    f"bash {ENSURE_PYTEST} (idempotent, age-gated: installs ops/install/requirements.txt, which "
    "declares pytest, into ~/.hermes-cortex/venv); or resolve an existing one with: "
    "bash ops/scripts/lib/python-with-module.sh --print pytest"
)


def _find_pytest() -> str | None:
    """The PYTHON only: the command shape below is `<interpreter> -m pytest`, so returning the
    `pytest` console script here would silently run `pytest -m pytest` and collect nothing.

    `PYTEST=<path>` is the documented escape hatch for a host that keeps an isolated venv. An
    override that is not a real file resolves to None rather than being handed back: a non-existent
    binary would surface the shell's own 126/127 as the test's result.
    """
    override = os.environ.get("PYTEST", "").strip()
    if override:
        return override if Path(override).is_file() else None
    if not RESOLVER.is_file():
        return None
    try:
        proc = subprocess.run(["bash", str(RESOLVER), "--print", "pytest"],
                              capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    resolved = proc.stdout.strip()
    return resolved if resolved and Path(resolved).is_file() else None


PYTEST = _find_pytest()

# Files this run could not JUDGE (no runner, or pytest collected nothing). Deliberately separate from
# `failures`: a file nothing ran is not evidence of a defect, and reporting it as one is how five
# files came to be called "pre-existing failures" on 2026-10-18 when four of them were never run.
not_run: list[str] = []

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
    # A non-Hermes caller's repo identity (titus/pi, 2026-10-09). IN SCOPE: this
    # change alters how a caller WITHOUT an injector resolves its repo, which is
    # exactly what decides whether end_change can release its lock at all.
    "tests/test_non_hermes_repo_identity.py",
    "tests/test_non_hermes_session_id.py",
    # The re-runnable reproduction behind the fix's evidence artifact. It ASSERTS
    # (pre-fix must refuse and strand the lock; current must release it) and exits
    # non-zero otherwise, so running it here means a future break in the release
    # path fails this artifact instead of only contradicting a committed prose claim.
    "tests/run_non_hermes_lock_release_repro.py",
    # The landing automation for that fix (a cron monitor gate), so its hermetic
    # probe test runs somewhere instead of being a guard nobody executes.
    "tests/test_land_when_clean_probe.py",
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
    # The interpreter resolver every deployed script can reach. Not loop-gov, but it is the
    # thing that decides WHO runs the other tests: a resolver that falls back to an
    # interpreter lacking the module makes a gate report a failure it never measured.
    "tests/test_python_with_module.py",
    # The guard on THIS harness. It pins the three facts the fix above depends on: pytest is
    # resolved through the committed resolver and never from a venv path this repo does not
    # create; the no-pytest case names a repair that is itself committed; and NOT RUN is printed
    # apart from RESULT, so a file that ran nothing cannot read as a clean pass (ADV-13116-1).
    # Its hermetic probe belongs here for the same reason as the resolver's: a guard nobody runs
    # is a guard nobody notices has rotted.
    "tests/test_run_loop_gov_regression_harness.py",
    # The CREATE step the resolution above depends on: idempotent, verified by import, age-gated.
    # Drives every branch (age gate refusing, a repair that leaves pytest unimportable, a missing
    # prerequisite) against a FABRICATED repo, so no branch is only exercised on a healthy host.
    "tests/test_ensure_pytest.py",
    # The loop_db embedding source of the session cache. It silently contributed
    # ZERO rows for months (phantom columns + a swallowed OperationalError), which
    # starves progress detection of its known-good patterns. This runs the fixed
    # query against hermetic fixtures and asserts the boundaries, so the next break
    # fails HERE instead of only contradicting a prose claim (ADV-12197-1).
    "tests/run_session_cache_loop_db_repro.py",
    # The weekly report's "Avg cycles per task" metric. It printed AVG(cycle_num)
    # under that label, contradicting the report's own Total/Unique lines; an
    # adversarial review read the mismatch as fabrication (ADV-12197-1).
    "tests/run_loop_evaluator_avg_per_task_repro.py",
]

GATE_FILE = "mcp-servers/loop-gov-mcp.py"
GATE_LEVEL = "A4"
# The revision everything in this artifact is compared AGAINST: the base of the range being
# reviewed, not `HEAD~1`. A relative revision degrades silently the moment another commit of your
# own lands — the artifact then compares a revision with ITSELF (which is how it once printed the
# same sha for both sides, ADV-11741-1) — and after the change is committed, `HEAD~1` is your own
# previous commit rather than the pre-fix tree. `merge-base origin/main HEAD` is the range base: it
# does not move as you commit, and it is the revision the close review diffs from.
def _range_base() -> str:
    """The base of the range under review. Resolved via git directly so this constant can be
    defined before the helpers below use it; falls back to HEAD~1 (the old behaviour) only when git
    cannot answer, and the artifact always prints the resolved sha."""
    try:
        proc = subprocess.run(["git", "merge-base", "origin/main", "HEAD"],
                              cwd=str(REPO), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return "HEAD~1"
    return proc.stdout.strip() or "HEAD~1"


PRE_FIX_REV = os.environ.get("LOOP_GOV_PRE_FIX_REV") or _range_base()


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


def _attribution_verdict(base_rc, cur_rc) -> str:
    """What a matching pair of exit codes MEANS. A result that reports a failure without saying
    whether the range introduced it is the claim a reviewer has to refuse; this is the sentence
    that answers it."""
    if base_rc is None:
        return "COULD NOT VERIFY — the file could not be run at the base revision"
    if base_rc == cur_rc:
        return "REPRODUCED at the base revision — this range did not introduce it"
    return "*** DIFFERS from the base revision — this range is implicated ***"


def _run_failing_at_base(base_rev: str, rels: list) -> tuple:
    """Run the FAILING files at `base_rev` in a throwaway worktree, with the SAME classification
    used above, and return ({rel: rc|None}, note). A failure the base reproduces is not this
    change's; a failure that DIFFERS is, and saying so is the whole point.

    A worktree that cannot be created yields None for every file, which `_attribution_verdict`
    reports as COULD NOT VERIFY — never as agreement.
    """
    results: dict = {rel: None for rel in rels}
    with tempfile.TemporaryDirectory(prefix="loop-gov-base-") as tmp:
        wt = Path(tmp) / "base"
        added = _run(["git", "worktree", "add", "-q", str(wt), base_rev], timeout=180)
        if added.returncode != 0:
            return results, f"could not create a worktree at {base_rev}: {added.stdout}{added.stderr}"
        try:
            for rel in rels:
                path = wt / rel
                if not path.is_file():
                    continue
                text = path.read_text(errors="ignore")
                if re.search(r"(?m)^def test_", text) and PYTEST:
                    cmd = [PYTEST, "-m", "pytest", "-q", str(path)]
                elif "__main__" in text:
                    cmd = [sys.executable, str(path)]
                elif PYTEST:
                    cmd = [PYTEST, "-m", "pytest", "-q", str(path)]
                else:
                    continue
                results[rel] = _run(cmd, cwd=wt).returncode
        finally:
            _run(["git", "worktree", "remove", "--force", str(wt)], timeout=180)
    return results, ""


def _result_block(failures: list, not_run: list) -> list:
    """The summary must separate the THREE outcomes: a file that ran nothing is not a pass and not
    a failure. Printing only `RESULT: ALL PASS` while files executed nothing is how five of them came
    to be called "pre-existing failures" on a host where four never ran."""
    block = [f"RESULT: {'ALL PASS' if not failures else 'FAILURES: ' + '; '.join(failures)}"]
    if not_run:
        block.append(f"NOT RUN ({len(not_run)}) — ran nothing, so they prove nothing either way:")
        block.extend(f"  - {entry}" for entry in not_run)
    return block


def main() -> int:
    revision = _git("rev-parse", "--short", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    out = []
    failures = []
    current_rc: dict = {}
    base_attribution: dict = {}

    out.append("loop-governance regression artifact")
    out.append("=" * 72)
    out.append(f"generated      : {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    out.append(f"revision under test : {revision}  (branch {branch}) — HEAD when this ran; the")
    out.append("                      artifact is committed BY the change it measures, so the")
    out.append(f"                      file under test is identical at the carrying commit")
    out.append(f"                      (`git diff <carrying-commit> {revision} -- {GATE_FILE}`).")
    out.append(f"pre-fix base        : {PRE_FIX_REV} ({_git('rev-parse', '--short', PRE_FIX_REV)})")
    out.append(f"interpreter    : Python {sys.version.split()[0]} (<python-bin>/python3)")
    out.append(f"generator      : tests/run_loop_gov_regression.py")
    out.append("")
    out.append("Re-run with:  LOOP_GOV_PRE_FIX_REV=" + PRE_FIX_REV +
               " python3 tests/run_loop_gov_regression.py")
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
        text = path.read_text(errors="ignore")
        # WHAT the file IS decides HOW to run it (2026-10-18, measured on the five files this
        # harness had mis-called "pre-existing failures"):
        #   * a file with `def test_` functions is PYTEST-STYLE. Running it directly is invalid even
        #     when it carries a legacy __main__ block: `test_python_with_module.py` needs tmp_path
        #     fixtures and `test_reviewer_backends.py` has a __main__ that fails while its 8 tests
        #     all pass. Under the old rule both read as FAILURES of the code, and they are not.
        #   * a file with NO test functions is a SCRIPT (`run_non_hermes_lock_release_repro`,
        #     `test_loop_gov_stale_purge`): direct execution is the only way to run it, so its rc is
        #     its real result — and pytest's rc=5 on it means "collected nothing", not "passed".
        # A mis-attributed failure discredits the changes nearest it, so the three outcomes are named.
        is_pytest_style = re.search(r"(?m)^def test_", text) is not None
        if is_pytest_style and PYTEST:
            cmd = [PYTEST, "-m", "pytest", "-q", rel]
        elif "__main__" in text:
            cmd = [sys.executable, rel]
        elif PYTEST:
            cmd = [PYTEST, "-m", "pytest", "-q", rel]
        else:
            not_run.append(f"{rel}: no __main__ runner, and {NO_PYTEST_HINT}")
            out.append(f"[NOT RUN] {rel} -- no __main__ runner; {NO_PYTEST_HINT}")
            continue
        proc = _run(cmd)
        if proc.returncode == 5:
            # pytest's "no tests collected" — the file ran nothing, so it proves nothing either way.
            not_run.append(f"{rel}: pytest collected no tests (rc=5)")
            out.append(f"[NOT RUN] {rel} -- pytest collected no tests (rc=5)")
            continue
        ok = proc.returncode == 0
        current_rc[rel] = proc.returncode
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
        prev_file.write_text(_git("show", PRE_FIX_REV + ":" + GATE_FILE))
        ok_prev, lines_prev = _gate(str(prev_file))
    out.append(f"[{'PASS' if ok_prev else 'FAIL'}] PRE-FIX revision {PRE_FIX_REV} "
               f"({_git('rev-parse', '--short', PRE_FIX_REV)})")
    for ln in lines_prev:
        out.append(f"        {ln}")
    out.append("")
    out.append("Comparison: the two summaries above must agree on their finding")
    out.append("counts (same total / medium / low / info), which is the claim that")
    out.append("this change introduces no new static findings.")
    out.append("")

    # ── 4. Attribution: does a failure belong to THIS range? ──
    # A failure count without an attribution is a claim a reviewer must refuse — "3 failed" cannot
    # say whether the range caused them. So every failure is re-run at the recorded base with the
    # SAME classification, and the pair of exit codes is what gets committed.
    if failures:
        rels = [f.split(":", 1)[0] for f in failures]
        base_rcs, note = _run_failing_at_base(PRE_FIX_REV, rels)
        base_attribution = base_rcs
        out.append("-" * 72)
        out.append(f"FAILURE ATTRIBUTION  base {PRE_FIX_REV} ({_git('rev-parse', '--short', PRE_FIX_REV)})"
                   f" vs this tree — same classification both sides")
        out.append("-" * 72)
        if note:
            out.append(f"  {note}")
        for rel in rels:
            verdict = _attribution_verdict(base_rcs.get(rel), current_rc.get(rel))
            out.append(f"  {rel}")
            out.append(f"        base rc={base_rcs.get(rel)}   this tree rc={current_rc.get(rel)}   {verdict}")
        out.append("")
        out.append("  A DIFFERS row is a regression from this range and must be treated as one.")
        out.append("")

    out.append("=" * 72)
    out.extend(_result_block(failures, not_run))
    out.append("=" * 72)

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text("\n".join(_scrub(ln) for ln in out) + "\n")

    print(f"artifact: {ARTIFACT}")
    print(f"revision: {revision}   tests: {len(TESTS)}")
    if failures:
        print(f"FAILURE ATTRIBUTION vs base {PRE_FIX_REV}:")
        for rel, base_rc in base_attribution.items():
            print(f"  {rel}: base rc={base_rc}  this tree rc={current_rc.get(rel)}"
                  f"  {_attribution_verdict(base_rc, current_rc.get(rel))}")
    if not_run:
        print(f"NOT RUN ({len(not_run)}) — ran nothing here, so they are NOT evidence either way:")
        for entry in not_run:
            print(f"  - {entry}")
    if failures:
        print("RESULT: FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("RESULT: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
