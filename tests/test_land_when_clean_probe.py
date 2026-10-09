#!/usr/bin/env python3
"""Hermetic tests for ops/scripts/manage/land-when-clean-probe.sh.

The probe is the no-LLM gate on a "land when clean" cron: the scheduler hashes
its stdout every tick and only wakes the agent when the text CHANGES. So the two
properties that matter are (a) the reported state is CORRECT and (b) the output is
STABLE while nothing changes. Prose about having tried it is not re-executable —
these cases build throwaway repos and assert the exact outputs and exit codes.

Run:  python3 tests/test_land_when_clean_probe.py    (also pytest-discoverable)
"""
import os
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "ops" / "scripts" / "manage" / "land-when-clean-probe.sh"

_FAIL: list = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        _FAIL.append(name)
        print(f"  FAIL  {name} — {detail}")


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def _mk_repo(tmp: Path, with_remote: bool = False, remote_commit: bool = False):
    """A throwaway repo, optionally with a bare `origin` that may already hold HEAD."""
    repo = tmp / "work"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    (repo / "tracked.txt").write_text("one\n")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-q", "-m", "seed")
    if not with_remote:
        return repo, None
    bare = tmp / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], capture_output=True)
    _git(repo, "remote", "add", "origin", str(bare))
    if remote_commit:
        _git(repo, "push", "-q", "-u", "origin", "main")
    return repo, bare


def _probe(repo: Path, *args):
    return subprocess.run(["bash", str(PROBE), "--repo", str(repo), *args],
                          capture_output=True, text=True)


def _fields(out: str) -> dict:
    fields = {}
    for token in out.split():
        if "=" in token:
            key, _, value = token.partition("=")
            fields[key] = value
    return fields


def test_dirty_path_is_reported_as_a_blocker():
    tmp = Path(tempfile.mkdtemp(prefix="probe-dirty-"))
    repo, _ = _mk_repo(tmp)
    (repo / "tracked.txt").write_text("changed\n")          # uncommitted edit
    proc = _probe(repo, "tracked.txt")
    fields = _fields(proc.stdout)
    check("dirty path -> blockers=1", fields.get("blockers") == "1", proc.stdout.strip())
    check("dirty path -> exit 0 (always reports)", proc.returncode == 0, str(proc.returncode))


def test_staged_change_also_counts():
    tmp = Path(tempfile.mkdtemp(prefix="probe-staged-"))
    repo, _ = _mk_repo(tmp)
    (repo / "tracked.txt").write_text("staged\n")
    _git(repo, "add", "tracked.txt")
    proc = _probe(repo, "tracked.txt")
    check("staged change -> blockers=1", _fields(proc.stdout).get("blockers") == "1",
          proc.stdout.strip())


def test_clean_path_reports_zero():
    tmp = Path(tempfile.mkdtemp(prefix="probe-clean-"))
    repo, _ = _mk_repo(tmp)
    proc = _probe(repo, "tracked.txt")
    check("clean path -> blockers=0", _fields(proc.stdout).get("blockers") == "0",
          proc.stdout.strip())
    check("clean path -> landed=n/a without --landed-commit",
          _fields(proc.stdout).get("landed") == "n/a", proc.stdout.strip())


def test_output_is_stable_across_runs():
    """The monitor suppresses the agent run on identical bytes — unstable output
    would wake it every tick."""
    tmp = Path(tempfile.mkdtemp(prefix="probe-stable-"))
    repo, _ = _mk_repo(tmp)
    (repo / "tracked.txt").write_text("changed\n")
    first = _probe(repo, "tracked.txt").stdout
    second = _probe(repo, "tracked.txt").stdout
    check("two runs are byte-identical", first == second, f"{first!r} vs {second!r}")


def test_landed_commit_is_detected_in_origin():
    tmp = Path(tempfile.mkdtemp(prefix="probe-landed-"))
    repo, _bare = _mk_repo(tmp, with_remote=True, remote_commit=True)
    head = _git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    proc = _probe(repo, "--landed-commit", head, "tracked.txt")
    check("commit pushed to origin -> landed=yes",
          _fields(proc.stdout).get("landed") == "yes", proc.stdout.strip())
    check("origin integrated -> origin_integrated=yes",
          _fields(proc.stdout).get("origin_integrated") == "yes", proc.stdout.strip())


def test_landed_commit_absent_from_origin_reports_no():
    tmp = Path(tempfile.mkdtemp(prefix="probe-notlanded-"))
    repo, _bare = _mk_repo(tmp, with_remote=True, remote_commit=False)
    head = _git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    proc = _probe(repo, "--landed-commit", head, "tracked.txt")
    check("unpushed commit -> landed=no", _fields(proc.stdout).get("landed") == "no",
          proc.stdout.strip())
    check("origin not integrated -> origin_integrated=no",
          _fields(proc.stdout).get("origin_integrated") == "no", proc.stdout.strip())


def test_missing_paths_is_a_usage_error():
    tmp = Path(tempfile.mkdtemp(prefix="probe-usage-"))
    repo, _ = _mk_repo(tmp)
    proc = subprocess.run(["bash", str(PROBE), "--repo", str(repo)],
                          capture_output=True, text=True)
    check("no paths -> exit 2", proc.returncode == 2, str(proc.returncode))
    check("no paths -> usage on stderr", "usage:" in proc.stderr, proc.stderr.strip()[:120])


def test_unreachable_repo_still_reports():
    """A probe must always print a line: a cron monitor reading nothing cannot tell
    'unchanged' from 'the probe broke'."""
    proc = subprocess.run(["bash", str(PROBE), "--repo", "/definitely/not/here", "x.txt"],
                          capture_output=True, text=True)
    out = proc.stdout.strip()
    check("unreachable repo -> exit 0", proc.returncode == 0, str(proc.returncode))
    check("unreachable repo -> every field unknown",
          out.startswith("repo=missing") and out.count("unknown") >= 4, out)


# ── the CONTENT landing test (--fixed-marker) ────────────────────────────────
# A SHA is rewritten when another session rebases a shared branch, and a commit
# SUBJECT can match unrelated work; file content can do neither. These cases pin
# that behaviour, including the false-positive control.

MARKER = "_session_repo_path"


def _repo_pushing(tmp: Path, content: str, subject: str = "work"):
    """A repo whose origin/main holds `content` in module.py."""
    repo, _bare = _mk_repo(tmp, with_remote=True, remote_commit=False)
    (repo / "module.py").write_text(content)
    _git(repo, "add", "module.py")
    _git(repo, "commit", "-q", "-m", subject)
    _git(repo, "push", "-q", "-u", "origin", "main")
    return repo


def test_content_marker_present_in_origin_lands():
    tmp = Path(tempfile.mkdtemp(prefix="probe-marker-yes-"))
    repo = _repo_pushing(tmp, f"def {MARKER}(): pass\n{MARKER}()\n{MARKER}()\n{MARKER}()\n")
    proc = _probe(repo, "--fixed-marker", f"module.py:{MARKER}:4", "tracked.txt")
    fields = _fields(proc.stdout)
    check("marker x4 in origin -> landed=yes", fields.get("landed") == "yes", proc.stdout.strip())
    check("marker count reported", fields.get("fix_in_origin") == "4", proc.stdout.strip())


def test_content_marker_below_minimum_does_not_land():
    tmp = Path(tempfile.mkdtemp(prefix="probe-marker-low-"))
    repo = _repo_pushing(tmp, f"def {MARKER}(): pass\n{MARKER}()\n")
    proc = _probe(repo, "--fixed-marker", f"module.py:{MARKER}:4", "tracked.txt")
    fields = _fields(proc.stdout)
    check("marker x2 < min 4 -> landed=no", fields.get("landed") == "no", proc.stdout.strip())
    check("marker count reported as 2", fields.get("fix_in_origin") == "2", proc.stdout.strip())


def test_matching_subject_without_the_marker_does_not_land():
    """The false positive the content test replaces: a commit whose MESSAGE carries
    the fix's subject but whose tree does not contain the change."""
    tmp = Path(tempfile.mkdtemp(prefix="probe-marker-falsepos-"))
    repo = _repo_pushing(tmp, "def unrelated(): pass\n",
                         subject="fix(governance): tag a non-Hermes session's lock with its OWN repo")
    proc = _probe(repo, "--fixed-marker", f"module.py:{MARKER}:4", "tracked.txt")
    fields = _fields(proc.stdout)
    check("matching subject, no marker -> landed=no", fields.get("landed") == "no",
          proc.stdout.strip())
    check("marker count 0", fields.get("fix_in_origin") == "0", proc.stdout.strip())


def test_marker_only_local_is_not_landed():
    """Origin is the authority: an unpushed fix is not landed."""
    tmp = Path(tempfile.mkdtemp(prefix="probe-marker-unpushed-"))
    repo, _bare = _mk_repo(tmp, with_remote=True, remote_commit=True)
    (repo / "module.py").write_text(f"{MARKER}\n{MARKER}\n{MARKER}\n{MARKER}\n")
    _git(repo, "add", "module.py")
    _git(repo, "commit", "-q", "-m", "local fix")
    proc = _probe(repo, "--fixed-marker", f"module.py:{MARKER}:4", "tracked.txt")
    fields = _fields(proc.stdout)
    check("marker only in the local commit -> landed=no", fields.get("landed") == "no",
          proc.stdout.strip())
    check("marker count 0 from origin's copy", fields.get("fix_in_origin") == "0",
          proc.stdout.strip())


def test_malformed_fixed_marker_is_a_usage_error():
    tmp = Path(tempfile.mkdtemp(prefix="probe-marker-bad-"))
    repo, _ = _mk_repo(tmp)
    proc = subprocess.run(
        ["bash", str(PROBE), "--repo", str(repo), "--fixed-marker", "module.py:marker",
         "tracked.txt"], capture_output=True, text=True)
    check("spec without MIN -> exit 2", proc.returncode == 2, str(proc.returncode))
    check("spec without MIN -> usage names the form",
          "--fixed-marker wants PATH:MARKER:MIN" in proc.stderr, proc.stderr.strip()[:160])


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for fn in tests:
        try:
            fn()
        except AssertionError as e:
            _FAIL.append(fn.__name__)
            print(f"  FAIL  {fn.__name__} — {e}")
        except Exception as e:  # noqa: BLE001
            _FAIL.append(fn.__name__)
            print(f"  FAIL  {fn.__name__} — {type(e).__name__}: {e}")
    print()
    if _FAIL:
        print(f"{len(_FAIL)} FAILED: {', '.join(_FAIL)}")
        raise SystemExit(1)
    print(f"ALL PASS ({len(tests)} cases)")


if __name__ == "__main__":
    main()
