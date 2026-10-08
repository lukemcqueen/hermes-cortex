#!/usr/bin/env python3
"""verify-landed.py: a check nobody can wave away, because each of its three parts can fail.

WHY: an operational cycle cannot carry committed evidence of its own success — the push is
last, so a transcript of it is written afterwards, changing the tip, invalidating the receipt
and leaving the deployed tree trailing. So the committed artifact must be a RE-RUNNABLE CHECK.
These tests prove each of its checks is real by making it fail in isolation:

  * a deployed copy that trails the tip            -> FAIL, naming the file (the loop's symptom)
  * a tip that is not on the remote                -> FAIL
  * a receipt that is missing, or not CLEAN        -> COULD NOT VERIFY / FAIL
  * --no-remote                                    -> the other checks still stand alone

Hermetic: a bare origin and a checkout under TMPDIR. No network, no host state.

Run: python3 -m pytest tests/test_verify_landed.py -q -s
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "ops" / "scripts" / "manage" / "verify-landed.py"


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def _run(*args):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True)


def _fixture(tmp):
    """A checkout with a bare origin, one registered source, and a fixture deploy map."""
    tmp = Path(tmp)
    _git(tmp, "init", "--bare", "-q", "origin.git")
    repo = tmp / "work" / "hermes-cortex"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    source = repo / "mcp-servers" / "loop-gov-mcp.py"
    source.parent.mkdir(parents=True)
    source.write_text("v1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "remote", "add", "origin", str(tmp / "origin.git"))
    _git(repo, "push", "-q", "-u", "origin", "main")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    deployed = tmp / "deploy" / "tools" / "loop-governance" / "loop-gov-mcp.py"
    deployed.parent.mkdir(parents=True)
    deployed.write_text("v1\n")
    manifest = tmp / "deploy" / "deploy-manifest.tsv"
    manifest.write_text(f"mcp-servers/loop-gov-mcp.py\t{deployed}\n")
    receipt_dir = tmp / "state"
    receipt_dir.mkdir()
    # The always-review list the GATE reads. A receipt is required only for a range that
    # touches one of these, so the fixture must carry the same list the gate would read.
    lib = repo / "ops" / "scripts" / "lib"
    lib.mkdir(parents=True)
    (lib / "always-review-paths.txt").write_text(
        "# always-review\nmcp-servers/loop-gov-mcp.py\n")
    # The shared validator the gate and this tool must BOTH use (one implementation).
    (lib / "review-receipt-check.py").write_text(
        (REPO / "ops" / "scripts" / "lib" / "review-receipt-check.py").read_text())
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "gate inputs")
    _git(repo, "push", "-q", "origin", "main")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()   # the range starts AFTER these
    return repo, source, base, deployed, manifest, receipt_dir


def _tip(repo):
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _receipt(receipt_dir, repo, tip, base, verdict="CLEAN"):
    """A receipt in the shape the WRITER produces, bound to the RANGE (tip AND base).

    Binding matters: a receipt earned for one range must not authorise another, so the
    fixture has to carry the real fields or it would test a shape the gate never sees.
    """
    (Path(receipt_dir) / f".reviewed-{repo.name}-{tip}.json").write_text(
        json.dumps({"verdict": verdict, "tip_sha": tip, "base_sha": base}))


def _args(repo, base, manifest, receipt_dir, extra=()):
    return ["--repo", str(repo), "--base", base, "--manifest", str(manifest),
            "--receipt-dir", str(receipt_dir), *extra]


def test_passes_when_all_three_checks_hold():
    with tempfile.TemporaryDirectory() as td:
        repo, source, base, deployed, manifest, receipt_dir = _fixture(td)
        source.write_text("v2\n")
        _git(repo, "commit", "-q", "-am", "change")
        _git(repo, "push", "-q", "origin", "main")
        tip = _tip(repo)
        deployed.write_text("v2\n")                      # the deploy caught up
        _receipt(receipt_dir, repo, tip, base)

        result = _run(*_args(repo, base, manifest, receipt_dir))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "All checks passed" in result.stdout, result.stdout
        print("  all three checks hold -> exit 0 ✓")


def test_a_deployed_copy_that_trails_the_tip_fails_and_names_the_file():
    """The loop's own symptom: committed after the deploy, so the deployed tree is stale."""
    with tempfile.TemporaryDirectory() as td:
        repo, source, base, deployed, manifest, receipt_dir = _fixture(td)
        source.write_text("v2\n")
        _git(repo, "commit", "-q", "-am", "change")
        _git(repo, "push", "-q", "origin", "main")
        _receipt(receipt_dir, repo, _tip(repo), base)           # deployed copy left at v1

        result = _run(*_args(repo, base, manifest, receipt_dir))
        assert result.returncode == 1, result.stdout
        assert "FAIL  deployed: mcp-servers/loop-gov-mcp.py" in result.stdout, result.stdout
        assert "deploy the tip, then re-run" in result.stdout, result.stdout
        print("  trailing deployed copy -> exit 1, file named ✓")


def test_a_deploy_header_on_the_deployed_copy_is_not_a_mismatch():
    """Deployed copies carry a header the deploy inserts AFTER the shebang, so a RAW hash
    never matches on either side, and neither does blindly dropping the first N lines.
    Hashing them raw reports a false FAIL for every registered text file — the same class of
    error as probing a path that does not exist: a probe that does not know the shape of the
    thing it is checking."""
    with tempfile.TemporaryDirectory() as td:
        repo, source, base, deployed, manifest, receipt_dir = _fixture(td)
        source.write_text("#!/usr/bin/env python3\nv2\n")
        _git(repo, "commit", "-q", "-am", "change")
        _git(repo, "push", "-q", "origin", "main")
        deployed.write_text("#!/usr/bin/env python3\n"
                            "# SOURCE: mcp-servers/loop-gov-mcp.py\n"
                            "# Do NOT edit this file — edit the source above and run: "
                            "bash cortex-update.sh\n"
                            "\n"
                            "v2\n")
        _receipt(receipt_dir, repo, _tip(repo), base)

        result = _run(*_args(repo, base, manifest, receipt_dir))
        assert result.returncode == 0, result.stdout
        assert "matches" in result.stdout, result.stdout
        print("  header after the shebang -> match, not a false FAIL ✓")


def test_a_tip_that_is_not_on_the_remote_fails():
    with tempfile.TemporaryDirectory() as td:
        repo, source, base, deployed, manifest, receipt_dir = _fixture(td)
        source.write_text("v2\n")
        _git(repo, "commit", "-q", "-am", "change")       # NOT pushed
        deployed.write_text("v2\n")
        _receipt(receipt_dir, repo, _tip(repo), base)

        result = _run(*_args(repo, base, manifest, receipt_dir))
        assert result.returncode == 1, result.stdout
        assert "FAIL  remote:" in result.stdout, result.stdout
        print("  unpushed tip -> exit 1 ✓")


def test_a_missing_receipt_is_could_not_verify_not_a_pass():
    with tempfile.TemporaryDirectory() as td:
        repo, source, base, deployed, manifest, receipt_dir = _fixture(td)
        source.write_text("v2\n")
        _git(repo, "commit", "-q", "-am", "change")
        _git(repo, "push", "-q", "origin", "main")
        deployed.write_text("v2\n")                       # no receipt written

        result = _run(*_args(repo, base, manifest, receipt_dir))
        assert result.returncode == 2, result.stdout
        assert "COULD NOT VERIFY" in result.stdout, result.stdout
        assert "not a pass" in result.stdout, result.stdout
        print("  missing receipt -> exit 2, not a pass ✓")


def test_a_receipt_that_is_not_clean_fails():
    with tempfile.TemporaryDirectory() as td:
        repo, source, base, deployed, manifest, receipt_dir = _fixture(td)
        source.write_text("v2\n")
        _git(repo, "commit", "-q", "-am", "change")
        _git(repo, "push", "-q", "origin", "main")
        deployed.write_text("v2\n")
        _receipt(receipt_dir, repo, _tip(repo), base, verdict="FINDINGS")

        result = _run(*_args(repo, base, manifest, receipt_dir))
        assert result.returncode == 1, result.stdout
        assert "verdict='FINDINGS'" in result.stdout, result.stdout
        print("  non-CLEAN receipt -> exit 1 ✓")


def test_no_remote_makes_the_other_checks_stand_alone():
    """Proves check 3 is separable: with an unpushed tip the other two still pass."""
    with tempfile.TemporaryDirectory() as td:
        repo, source, base, deployed, manifest, receipt_dir = _fixture(td)
        source.write_text("v2\n")
        _git(repo, "commit", "-q", "-am", "change")       # never pushed
        deployed.write_text("v2\n")
        _receipt(receipt_dir, repo, _tip(repo), base)

        with_remote = _run(*_args(repo, base, manifest, receipt_dir))
        without_remote = _run(*_args(repo, base, manifest, receipt_dir, extra=("--no-remote",)))
        assert with_remote.returncode == 1, with_remote.stdout
        assert without_remote.returncode == 0, without_remote.stdout
        assert "remote sync: skipped (--no-remote)" in without_remote.stdout
        print("  --no-remote isolates the remote check ✓")


def test_a_missing_map_is_could_not_verify():
    with tempfile.TemporaryDirectory() as td:
        repo, source, base, deployed, manifest, receipt_dir = _fixture(td)
        source.write_text("v2\n")
        _git(repo, "commit", "-q", "-am", "change")
        _git(repo, "push", "-q", "origin", "main")
        _receipt(receipt_dir, repo, _tip(repo), base)

        result = _run(*_args(repo, base, Path(td) / "no-such-map.tsv", receipt_dir))
        assert result.returncode == 2, result.stdout
        assert "NOT checked" in result.stdout, result.stdout
        print("  missing deploy map -> exit 2, says what was NOT checked ✓")


# ── the receipt rule must MIRROR THE GATE, not approximate it ───────────────────
# The gate requires a receipt only for a range that touches an always-review path
# (ops/scripts/lib/always-review-paths.txt). Demanding one unconditionally turns a
# legitimately unreviewed docs-only push into "COULD NOT VERIFY" — a false alarm that
# trains the reader to ignore the tool. The mirror also has to be COMPLETE: the gate
# validates the receipt's tip AND base through the shared validator, so a receipt
# earned for another range must not satisfy this one.

def test_a_range_that_touches_no_always_review_path_needs_no_receipt():
    """A docs-only push the gate allows without a receipt must verify CLEAN, not rc=2.

    This is the regression: the tool demanded a receipt unconditionally, so the very
    push that exposed it (base 399eda41..tip 4c4ae92c, docs and skills only) returned
    COULD NOT VERIFY while the gate itself had correctly required nothing.
    """
    with tempfile.TemporaryDirectory() as td:
        repo, source, base, deployed, manifest, receipt_dir = _fixture(td)
        (repo / "docs").mkdir()
        (repo / "docs" / "notes.md").write_text("a docs-only change\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "docs only")
        _git(repo, "push", "-q", "origin", "main")
        # deliberately NO receipt: the gate does not need one for this range
        result = _run(*_args(repo, base, manifest, receipt_dir))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "not required" in result.stdout, result.stdout
        assert "no always-review path" in result.stdout, result.stdout
        print("  docs-only range, no receipt -> exit 0, 'not required' ✓")


def test_an_always_review_range_still_cannot_verify_without_a_receipt():
    """The mirror must not weaken the gate: an always-review path still needs one."""
    with tempfile.TemporaryDirectory() as td:
        repo, source, base, deployed, manifest, receipt_dir = _fixture(td)
        source.write_text("v2\n")                     # always-review path
        _git(repo, "commit", "-q", "-am", "enforcement change")
        _git(repo, "push", "-q", "origin", "main")
        deployed.write_text("v2\n")                   # only the receipt is missing
        result = _run(*_args(repo, base, manifest, receipt_dir))
        assert result.returncode == 2, result.stdout
        assert "COULD NOT VERIFY" in result.stdout, result.stdout
        assert "mcp-servers/loop-gov-mcp.py" in result.stdout, result.stdout
        print("  always-review range without a receipt -> exit 2, path named ✓")


def test_a_receipt_earned_for_another_range_does_not_authorise_this_one():
    """Bound to tip AND base: a receipt for a different range is not CLEAN for this one."""
    with tempfile.TemporaryDirectory() as td:
        repo, source, base, deployed, manifest, receipt_dir = _fixture(td)
        source.write_text("v2\n")
        _git(repo, "commit", "-q", "-am", "change")
        _git(repo, "push", "-q", "origin", "main")
        deployed.write_text("v2\n")
        _receipt(receipt_dir, repo, _tip(repo), "0" * 40)   # right tip, WRONG base
        result = _run(*_args(repo, base, manifest, receipt_dir))
        assert result.returncode == 1, result.stdout
        assert "FAIL  receipt:" in result.stdout, result.stdout
        print("  receipt bound to another range -> exit 1 ✓")


def test_a_receipt_bound_to_this_range_authorises_it():
    with tempfile.TemporaryDirectory() as td:
        repo, source, base, deployed, manifest, receipt_dir = _fixture(td)
        source.write_text("v2\n")
        _git(repo, "commit", "-q", "-am", "change")
        _git(repo, "push", "-q", "origin", "main")
        deployed.write_text("v2\n")
        _receipt(receipt_dir, repo, _tip(repo), base)
        result = _run(*_args(repo, base, manifest, receipt_dir))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "verdict=CLEAN" in result.stdout, result.stdout
        print("  receipt bound to this range -> exit 0 ✓")


def test_a_short_base_resolves_to_the_receipts_range():
    """`--base` may be given short; the comparison must be on CANONICAL revisions.

    Regression (2026-10-08): the tool resolved the TIP through `git rev-parse` but passed
    `--base` through verbatim, so a short base never matched a receipt's full base_sha and
    a VALID receipt was reported as not authorising the range. The push gate contradicted
    it (it resolves merge-base to a full sha and allowed the push), which is what exposed
    the false FAIL. Every earlier range had been docs-only, so the comparison was never
    reached: 'receipt: not required' returned first.
    """
    with tempfile.TemporaryDirectory() as td:
        repo, source, base, deployed, manifest, receipt_dir = _fixture(td)
        source.write_text("v2\n")
        _git(repo, "commit", "-q", "-am", "change")
        _git(repo, "push", "-q", "origin", "main")
        deployed.write_text("v2\n")
        _receipt(receipt_dir, repo, _tip(repo), base)     # receipt carries FULL shas
        short = base[:8]
        assert len(short) < 40, "the fixture must exercise a short rev"
        result = _run(*_args(repo, short, manifest, receipt_dir))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "verdict=CLEAN" in result.stdout, result.stdout
        # ...and a REAL but different base must still be refused (no over-permission)
        other = _git(repo, "rev-list", "--max-parents=0", "HEAD").stdout.strip()
        assert other and other != base, "the control base must be a real, different revision"
        result_other = _run(*_args(repo, other, manifest, receipt_dir))
        assert result_other.returncode == 1, result_other.stdout
        assert "does not authorise" in result_other.stdout, result_other.stdout
        # ...and a base git cannot resolve is COULD NOT VERIFY, never a pass: an
        # unresolvable rev makes `git diff` fail, which yields an empty range, and an
        # empty range would otherwise read as "no always-review path -> not required".
        result_bogus = _run(*_args(repo, "0" * 40, manifest, receipt_dir))
        assert result_bogus.returncode == 2, result_bogus.stdout
        assert "COULD NOT VERIFY" in result_bogus.stdout, result_bogus.stdout
        print("  short --base resolves ✓; a foreign base is refused ✓; a bogus base cannot verify ✓")


def _main():
    """Standalone runner.

    A pytest-style file with no runner imports, executes nothing and exits 0 — so any
    harness recording `rc=0` scores it PASS. Prove a test RAN by its output, not its
    exit code: this prints one line per case and fails loudly if a case does not run.
    """
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    if not tests:
        print("NO TESTS RAN — this file executed nothing")
        return 1
    print(f"running {len(tests)} case(s)")
    for name, fn in tests:
        fn()
        print(f"[PASS] {name}")
    print(f"RESULT: ALL PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())