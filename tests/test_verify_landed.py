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
    return repo, source, base, deployed, manifest, receipt_dir


def _tip(repo):
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _receipt(receipt_dir, repo, tip, verdict="CLEAN"):
    (Path(receipt_dir) / f".reviewed-{repo.name}-{tip}.json").write_text(
        json.dumps({"verdict": verdict}))


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
        _receipt(receipt_dir, repo, tip)

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
        _receipt(receipt_dir, repo, _tip(repo))           # deployed copy left at v1

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
        _receipt(receipt_dir, repo, _tip(repo))

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
        _receipt(receipt_dir, repo, _tip(repo))

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
        _receipt(receipt_dir, repo, _tip(repo), verdict="FINDINGS")

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
        _receipt(receipt_dir, repo, _tip(repo))

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
        _receipt(receipt_dir, repo, _tip(repo))

        result = _run(*_args(repo, base, Path(td) / "no-such-map.tsv", receipt_dir))
        assert result.returncode == 2, result.stdout
        assert "NOT checked" in result.stdout, result.stdout
        print("  missing deploy map -> exit 2, says what was NOT checked ✓")