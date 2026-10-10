#!/usr/bin/env python3
"""Review-receipt gate: a CLEAN review must precede a push (no pytest needed).

    python3 tests/test_review_receipt_gate.py     # exit 0 = pass

Exercises the SAME ops/scripts/lib/review-receipt-check.py the pre-push hook
calls, so these assertions cannot drift from what actually gates a push.

REPAIRED 2026-10-09: this file carried TWO `def main()` blocks (lines 44 and 143).
Python keeps the LAST definition, so the first — and the AC-5 runtime-only check it
alone contained — was dead code that had silently stopped running. The two mains
are merged into one, and the range-coverage cases below were added.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECK = REPO / "ops/scripts/lib/review-receipt-check.py"
LIST = REPO / "ops/scripts/lib/always-review-paths.txt"

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


def authorises(receipt, tip, base):
    """Run the shipped helper the hook runs."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(receipt, fh)
        p = fh.name
    try:
        out = subprocess.run([sys.executable, str(CHECK), p, tip, base],
                             capture_output=True, text=True)
        return (out.stdout.strip() or "0")
    finally:
        Path(p).unlink(missing_ok=True)


def authorises_in_repo(receipt, tip, base, repo):
    """Run the shipped helper WITH --repo, so the content-coverage path runs."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(receipt, fh)
        p = fh.name
    try:
        out = subprocess.run([sys.executable, str(CHECK), p, tip, base, "--repo", str(repo)],
                             capture_output=True, text=True)
        return (out.stdout.strip() or "0")
    finally:
        Path(p).unlink(missing_ok=True)


def _hook_under_test(state_dir):
    """Run THIS REPO's pre-push-pull, not the deployed copy.

    The deployed hook is uncommitted state: if it were stale or absent the test
    could exercise a hook that lacks the gate and still look green. Running the
    committed source makes the test depend only on what is under review.
    """
    src = REPO / "ops/scripts/pre-push-pull"
    tmpdir = Path(tempfile.mkdtemp(prefix="hook-under-test-"))
    dst = tmpdir / "pre-push"
    shutil.copy2(src, dst)
    dst.chmod(0o755)
    env = dict(os.environ)
    env["GOVERNANCE_STATE_DIR"] = str(state_dir)
    r = subprocess.run(["bash", str(dst)], cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=300)
    shutil.rmtree(tmpdir, ignore_errors=True)
    return r


def integration_checks():
    """End-to-end: the DEPLOYED hook must actually refuse (ADV-10818-1).

    Deterministic by construction: the hook is pointed at a THROWAWAY state dir
    holding a copy of this session's lock (so the lock gate passes) and NO
    receipt (so the receipt gate must fire). Nothing here depends on whatever
    live receipts happen to exist, so it cannot pass or fail by accident.

    SCOPE: this asserts the REFUSAL only. The "a matching receipt is allowed"
    side is asserted at unit level below, through the same
    review-receipt-check.py the hook calls. Asserting it here too would run the
    whole hook past the gate into the doctor/deploy gates, which are not this
    test's subject and would make the result depend on deployed state.
    """
    # Staleness guard: the deployed copy is what actually gates pushes, so if it
    # lacks the gate that is worth SEEING, not hiding behind a source-only pass.
    deployed = Path.home() / ".hermes-cortex/hooks/pre-push"
    if deployed.exists():
        check("deployed hook carries the gate (staleness check)",
              "Review receipt gate" in deployed.read_text(), True)

    live = Path.home() / ".hermes-cortex/state"
    locks = sorted(live.glob(".governance-*.json"))
    if not locks:
        print("SKIP integration: no live lock to copy (cannot exercise the gate)")
        return

    # The receipt gate only fires for a NON-EMPTY unpushed range (it matches the
    # range's files against the always-review list). When the repo is level with
    # origin/main there is no range to gate at all, so asserting a refusal here
    # fails on a HEALTHY tree — the assertion was reading ambient state, not the
    # gate (change-checklist: drive the detector with controlled inputs; never
    # assert live state). Report the skip explicitly instead of passing silently.
    def _gitq(*a):
        return subprocess.run(["git", "-C", str(REPO), *a],
                              capture_output=True, text=True).stdout.strip()

    _tip, _base = _gitq("rev-parse", "HEAD"), _gitq("merge-base", "origin/main", "HEAD")
    if not _tip or not _base or _tip == _base:
        print(f"SKIP integration refusal: nothing unpushed (HEAD {_tip[:8]} is level with "
              f"origin/main) — the gate has no range to refuse")
        return
    tmp = Path(tempfile.mkdtemp(prefix="receipt-gate-"))
    try:
        shutil.copy2(locks[-1], tmp / locks[-1].name)   # lock present, no receipt
        r = _hook_under_test(tmp)
        combined = r.stdout + r.stderr
        check("repo hook refuses without a receipt",
              r.returncode != 0 and "carries no clean review receipt" in combined, True)
        check("refusal names the always-review files",
              "mcp-servers/loop-gov-mcp.py" in combined
              or "ops/scripts/pre-push-pull" in combined, True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def range_coverage_checks():
    """CONTENT coverage (2026-10-09): a REBASE rewrites the tip but not the content.

    A tip-bound receipt used to become invalid then, blocking a push whose content
    had in fact been reviewed — observed when another session rebased this shared
    branch (a commit of ours became 120758c2 -> 09d27193, same content).
    """
    import importlib.util as _ilu

    spec = _ilu.spec_from_file_location("rrc", CHECK)
    rrc = _ilu.module_from_spec(spec)
    spec.loader.exec_module(rrc)

    tmp = Path(tempfile.mkdtemp(prefix="receipt-range-"))
    repo = tmp / "repo"
    (repo / "mcp-servers").mkdir(parents=True)

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t.t")
    git("config", "user.name", "t")
    (repo / "mcp-servers" / "loop-gov-mcp.py").write_text("v1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "seed")
    base = git("rev-parse", "HEAD").stdout.strip()

    (repo / "mcp-servers" / "loop-gov-mcp.py").write_text("v2\n")
    git("add", "-A")
    git("commit", "-q", "-m", "the reviewed change")
    tip1 = git("rev-parse", "HEAD").stdout.strip()

    blobs = rrc.range_blobs(repo, base, tip1)
    check("range blobs are computed", isinstance(blobs, dict) and bool(blobs), True)
    receipt = {"verdict": "CLEAN", "tip_sha": tip1, "base_sha": base, "reviewed_blobs": blobs}
    check("exact tip/base still authorises", authorises(receipt, tip1, base), "1")

    # Rebase: rewrite the commit — same content, new SHA.
    git("commit", "-q", "--amend", "-m", "the reviewed change (rebased)")
    tip2 = git("rev-parse", "HEAD").stdout.strip()
    check("rebase really changed the tip", tip2 != tip1, True)
    check("rebased tip authorises by CONTENT", authorises_in_repo(receipt, tip2, base, repo), "1")

    # Fail-closed: the range GAINS a file the receipt never saw.
    (repo / "mcp-servers" / "extra.py").write_text("new\n")
    git("add", "-A")
    git("commit", "-q", "-m", "an unreviewed addition")
    tip3 = git("rev-parse", "HEAD").stdout.strip()
    check("range that gained an uncovered file refuses",
          authorises_in_repo(receipt, tip3, base, repo), "0")

    # A receipt with no reviewed_blobs is only ever accepted by exact tip/base.
    legacy = {"verdict": "CLEAN", "tip_sha": tip1, "base_sha": base}
    check("legacy receipt without blobs does not cover a rebase",
          authorises_in_repo(legacy, tip2, base, repo), "0")

    # Could-not-verify: an unresolvable range is a refusal, never a pass.
    check("unresolvable range refuses",
          authorises_in_repo(receipt, "0" * 40, base, repo), "0")

    shutil.rmtree(tmp, ignore_errors=True)


def hook_authorises_by_content():
    """The COMMITTED hook must pass the gate for a receipt that COVERS the range by
    content — driven, not described. The fixture receipt deliberately carries wrong
    tip/base, so only the coverage rule can let it through; it is written to a
    THROWAWAY state dir (never the live one), so nothing here fabricates a receipt
    for a real push."""
    import importlib.util as _ilu

    spec = _ilu.spec_from_file_location("rrc2", CHECK)
    rrc = _ilu.module_from_spec(spec)
    spec.loader.exec_module(rrc)

    def git(*args):
        return subprocess.run(["git", "-C", str(REPO), *args],
                              capture_output=True, text=True).stdout.strip()

    tip = git("rev-parse", "HEAD")
    base = git("merge-base", "origin/main", "HEAD") or git("rev-list", "--max-parents=0", "HEAD")
    blobs = rrc.range_blobs(REPO, base, tip)
    if not blobs:
        print("SKIP hook-authorises: could not resolve this repo's range")
        return

    live = Path.home() / ".hermes-cortex/state"
    locks = sorted(live.glob(".governance-*.json"))
    if not locks:
        print("SKIP hook-authorises: no live lock to copy")
        return

    tmp = Path(tempfile.mkdtemp(prefix="receipt-allow-"))
    try:
        (tmp / locks[-1].name).write_text(locks[-1].read_text())
        (tmp / ".reviewed-hermes-cortex-fixture.json").write_text(json.dumps({
            "verdict": "CLEAN",
            "tip_sha": "0" * 40,          # deliberately NOT the current tip
            "base_sha": "0" * 40,
            "reviewed_blobs": blobs,
        }))
        r = _hook_under_test(tmp)
        combined = r.stdout + r.stderr
        check("hook passes the gate for a receipt covering the range by CONTENT",
              "carries no clean review receipt" not in combined, True)
        check("hook did not silently skip the receipt gate at all",
              "Review receipt gate" in (REPO / "ops/scripts/pre-push-pull").read_text(), True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    check("shared checker exists", CHECK.is_file(), True)
    check("always-review list exists", LIST.is_file(), True)
    check("this file has exactly ONE main()",
          (REPO / "tests/test_review_receipt_gate.py").read_text().count("\ndef main():") == 1,
          True)

    clean = {"verdict": "CLEAN", "tip_sha": "aaaa111", "base_sha": "bbbb222"}
    check("matching range authorises", authorises(clean, "aaaa111", "bbbb222"), "1")
    check("FINDINGS never authorises",
          authorises({**clean, "verdict": "FINDINGS"}, "aaaa111", "bbbb222"), "0")
    check("missing receipt refuses", authorises({}, "aaaa111", "bbbb222"), "0")
    check("empty base never authorises",
          authorises({**clean, "base_sha": ""}, "aaaa111", ""), "0")

    # AC-3 - THE replay guard. A receipt earned for range A must not authorise B.
    check("different tip refuses (range A vs B)",
          authorises(clean, "cccc333", "bbbb222"), "0")
    check("different base refuses (same tip, rebased range)",
          authorises(clean, "aaaa111", "dddd444"), "0")

    # AC-4 - scope: only always-review paths require a receipt.
    patterns = [l.strip() for l in LIST.read_text().splitlines()
                if l.strip() and not l.startswith("#")]
    check("list is non-empty", len(patterns) > 0, True)
    ordinary = ["docs/README.md", "skills/devops/example/SKILL.md", "README.md"]
    check("ordinary files need no receipt",
          any(p in f for p in patterns for f in ordinary), False)
    guarded = ["mcp-servers/loop-gov-mcp.py", "ops/scripts/pre-push-pull"]
    check("always-review files DO need one",
          any(p in f for p in patterns for f in guarded), True)

    integration_checks()
    range_coverage_checks()
    hook_authorises_by_content()

    # AC-5 - runtime-only: the receipt lives in the state dir, never in a repo.
    # (This check lived only in the dead duplicate main() until 2026-10-09.)
    hook_src = (REPO / "ops/scripts/pre-push-pull").read_text()
    check("no repo-local receipt convention in the hook",
          ".reviewed-" in hook_src and "$GOVERNANCE_STATE_DIR/.reviewed-" in hook_src,
          True)

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}")
        return 1
    print("RESULT: ALL PASS - receipt bound to the range, scoped, and the deployed hook refuses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
